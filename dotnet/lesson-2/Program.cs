// Lesson 2 (C# / .NET 8) — an MCP server exposing the Lesson 1 retriever as tools.
//
// A faithful port of the Python reference (`mcp_server.py`). It wraps the same
// document search you built in the C# Lesson 1 port (`dotnet/lesson-1`) as
// Model Context Protocol tools, so an MCP host like Claude Code can search your
// local `documents/` folder natively instead of you pasting text into a prompt.
//
// Two modes (the run.sh dispatcher passes the action as the first argument):
//   serve         run the MCP server over stdio (a host/client connects to it)
//   demo | test   spawn the server and drive it through the SDK's stdio client
//
// Built on the official ModelContextProtocol C# SDK.

using System.ComponentModel;
using System.Reflection;
using LocalRag;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using ModelContextProtocol.Server;

var action = args.Length > 0 ? args[0] : "serve";

if (action is "demo" or "test" or "client")
{
    var query = args.Length > 1 ? args[1] : "How do I reset the device?";
    await DemoClient.RunAsync(query);
    return;
}

// Default: run the MCP server over stdio — exactly how a host like Claude Code
// launches a local server.
var builder = Host.CreateApplicationBuilder(args);
// Route ALL logs to stderr so they never corrupt the JSON-RPC stream on stdout.
builder.Logging.AddConsole(o => o.LogToStandardErrorThreshold = LogLevel.Trace);
builder.Services
    .AddMcpServer()
    .WithStdioServerTransport()
    .WithToolsFromAssembly();
await builder.Build().RunAsync();

// ---------------------------------------------------------------------------
// Tools — discovered by WithToolsFromAssembly(). The [Description] attributes
// ARE the prompt: the model reads them to decide when to call each tool.
[McpServerToolType]
public static class DocTools
{
    [McpServerTool(Name = "search_docs"), Description(
        "Search the user's local documents and return the most relevant passages. " +
        "Each passage is prefixed with its source as [filename:page] so the model " +
        "can cite it. Call this to ground answers in the user's own files instead " +
        "of relying on training data.")]
    public static string SearchDocs(
        [Description("What to search for, in natural language.")] string query,
        [Description("How many passages to return (default 5).")] int k = 5)
    {
        var config = Config.Load();
        var hits = GetRetriever(config).Search(query, Math.Max(1, k));
        if (hits.Count == 0)
        {
            return "No relevant passages found in the local documents.";
        }
        return string.Join("\n\n", hits.Select(h => $"[{h.Source}:{h.PageNumber}] {h.Text}"));
    }

    [McpServerTool(Name = "list_documents"), Description(
        "List the documents currently available to search in the local corpus.")]
    public static string ListDocuments()
    {
        var config = Config.Load();
        var names = Extract.DiscoverFiles(config.DocsDir).Select(Path.GetFileName).ToList();
        return names.Count > 0 ? string.Join("\n", names) : "(no documents indexed yet)";
    }

    // Mirror Engine.GetRetriever without pulling in Providers/Prompts: rebuild
    // the on-disk index when the docs change, then build a BM25 retriever.
    private static IRetriever GetRetriever(Config config)
    {
        if (Store.IsStale(config))
        {
            Store.BuildIndex(config);
        }
        return RetrieverFactory.BuildRetriever(Store.LoadChunks(config), config);
    }
}

// ---------------------------------------------------------------------------
// Demo client — spawns this same binary in `serve` mode over stdio (exactly as
// an MCP host would), lists the tools, and calls them. No LLM needed.
public static class DemoClient
{
    public static async Task RunAsync(string query)
    {
        // Re-launch ourselves as the server: `dotnet <thisAssembly>.dll serve`.
        var dll = Assembly.GetEntryAssembly()!.Location;
        var transport = new StdioClientTransport(new StdioClientTransportOptions
        {
            Name = "local-ai-lab-docs-dotnet",
            Command = "dotnet",
            Arguments = [dll, "serve"],
        });
        var client = await McpClient.CreateAsync(transport);

        // The handshake in code: CreateAsync does initialize, then list + call.
        var tools = await client.ListToolsAsync();
        Console.WriteLine("Connected to MCP server. Tools: " +
            string.Join(", ", tools.Select(t => t.Name)));

        var docs = await client.CallToolAsync("list_documents", new Dictionary<string, object?>());
        Console.WriteLine("\nlist_documents ->");
        Console.WriteLine(TextOf(docs));

        Console.WriteLine($"\nsearch_docs(\"{query}\", k=3) ->");
        var res = await client.CallToolAsync(
            "search_docs",
            new Dictionary<string, object?> { ["query"] = query, ["k"] = 3 });
        Console.WriteLine(TextOf(res));
    }

    private static string TextOf(CallToolResult result) =>
        string.Concat(result.Content.OfType<TextContentBlock>().Select(c => c.Text));
}
