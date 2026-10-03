// Lesson 10 - the System One wire format, by hand (port of python/systemone.py).
//
// A request is one `state` plus named, typed `questions`; the answer is a
// probability for every option of every question. This file builds requests,
// fingerprints them for the cassettes, checks the answers' shape, and sends one
// request to TypeSafe or to a loopback adapter. Reference: https://docs.typesafe.ai/api

using System.Diagnostics;
using System.Net;
using System.Numerics;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Lesson10Jev;

/// <summary>One answer, as the policy and scorecard read it. Probs is in option order.</summary>
public sealed record Answer(string Pick, List<KeyValuePair<string, double>> Probs, double Confidence)
{
    public double Prob(string label, double fallback)
    {
        foreach (var kv in Probs) if (kv.Key == label) return kv.Value;
        return fallback;
    }
}

public static class SystemOne
{
    public const string TypeSafeUrl = "https://api.typesafe.ai";
    public const string Path = "/v1/systemone";

    /// <summary>The labels a question can be answered with, in order.</summary>
    public static List<string> Options(Dict q) => q["type"] switch
    {
        "noul" => new List<string> { "yes", "no" },
        "choice" => ((Dict)q["criteria"]!).Keys.ToList(),
        "score" => ((List<object?>)q["criteria"]!).Select(x => (string)x!).ToList(),
        var kind => throw new ArgumentException($"unknown question type {Py.Repr(kind)}"),
    };

    /// <summary>What TypeSafe would reject with HTTP 422, checked before anything is sent.</summary>
    public static List<string> RequestProblems(object? bodyValue)
    {
        if (bodyValue is not Dict body) return new List<string> { "body: a JSON object" };
        var found = new List<string>();
        if (body.Get("model") is not string { Length: > 0 }) found.Add("model: required");
        if (!body.Has("state")) found.Add("state: required");
        if (body.Get("questions") is not Dict { Count: > 0 } questions)
        {
            found.Add("questions: at least one question");
            return found;
        }
        if (questions.Count > 64) found.Add($"questions: at most 64, got {questions.Count}");
        foreach (var (name, value) in questions.Items)
        {
            if (value is not Dict q)
            {
                found.Add($"questions.{name}: an object");
                continue;
            }
            var kind = q.Get("type");
            if (kind is not ("noul" or "choice" or "score"))
            {
                found.Add($"questions.{name}.type: noul, choice or score");
                continue;
            }
            if (!Py.Truthy(q.Get("instructions"))) found.Add($"questions.{name}.instructions: required");
            var criteria = q.Get("criteria");
            if (kind is "choice" && !(criteria is Dict { Count: >= 2 and <= 255 }))
                found.Add($"questions.{name}.criteria: 2-255 options");
            if (kind is "score" && !(criteria is List<object?> { Count: >= 2 and <= 10 }))
                found.Add($"questions.{name}.criteria: 2-10 levels");
        }
        return found;
    }

    public static Dict BuildRequest(object? state, Dict questions, string model = "jev-latest")
    {
        var body = new Dict { ["model"] = model, ["state"] = state, ["questions"] = questions };
        var problems = RequestProblems(body);
        if (problems.Count > 0) throw new ArgumentException(string.Join("; ", problems));
        return body;
    }

    /// <summary>A short fingerprint of exactly what was asked, used to refuse stale recordings.</summary>
    public static string Digest(Dict body)
    {
        var blob = Py.Canonical(new Dict { ["state"] = body["state"], ["questions"] = body["questions"] });
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(blob))).ToLowerInvariant()[..16];
    }

    /// <summary>
    /// Turn a System One response into {question: Answer}, plus what was missing or malformed.
    ///
    /// The three answer types arrive in three shapes. This gives them one: Pick is always a
    /// label from Options() ("yes"/"no" for a noul, the level name for a score) and Probs maps
    /// every label to its probability. The policy and the scorecard only see this shape, so
    /// they cannot tell TypeSafe's Jev from a local adapter or the keyword rules.
    /// With a real System One model the list of problems stays empty.
    /// </summary>
    public static (Dictionary<string, Answer> Answers, List<string> Problems) ReadAnswers(Dict questions, object? response)
    {
        var answers = new Dictionary<string, Answer>();
        var problems = new List<string>();
        // A reply that is not an object (or has no "answers" object) answers nothing.
        var got = response is Dict r0 && r0.Get("answers") is Dict g ? g : new Dict();
        foreach (var (name, value) in questions.Items)
        {
            var q = (Dict)value!;
            var kind = (string)q["type"]!;
            var labels = Options(q);
            // The answer must be of the type that was asked: a noul for a noul, and so on.
            if (got.Get(name) is not Dict a || a.Get("type") as string != kind)
            {
                problems.Add($"{name}: no {kind} answer");
                continue;
            }
            string pick;
            List<KeyValuePair<string, double>> probs;
            double confidence;
            if (kind == "noul")
            {
                // noul: one number, P(yes). Split it into yes/no so it looks like the other types.
                var p = a.Get("noul");
                if (!Py.IsProbability(p))
                {
                    problems.Add($"{name}: noul must be a number in [0, 1]");
                    continue;
                }
                double x = Py.Num(p);
                probs = new() { new("yes", x), new("no", 1.0 - x) };
                pick = x >= 0.5 ? "yes" : "no";
                confidence = Math.Max(x, 1 - x);
            }
            else
            {
                // choice and score: a probability per option.
                var raw = a.Get("probabilities") is Dict r ? r : new Dict();
                if (kind == "score")
                {
                    // A score's keys are level numbers ("0", "1", ...): translate them to level names.
                    var mapped = new Dict();
                    foreach (var (k, v) in raw.Items)
                    {
                        if (Regex.IsMatch(k, @"\A[0-9]+\z") && k.TrimStart('0').Length <= 3 && int.Parse(k, Py.Inv) < labels.Count)
                            mapped[labels[int.Parse(k, Py.Inv)]] = v;
                    }
                    raw = mapped;
                }
                // Valid means: exactly the question's options, each a real probability, summing to 1.
                bool numeric = raw.Items.All(kv => Py.IsProbability(kv.Value));
                bool sameSet = raw.Count == labels.Distinct().Count() && raw.Keys.All(labels.Contains);
                if (!sameSet || !numeric || Math.Abs(Py.FSum(raw.Items.Select(kv => kv.Value)) - 1.0) > 0.01)
                {
                    problems.Add($"{name}: probabilities must cover {Py.Repr(labels)} and sum to 1");
                    continue;
                }
                probs = labels.Select(l => new KeyValuePair<string, double>(l, Py.Num(raw[l]))).ToList();
                object? chosen;
                if (kind == "choice")
                {
                    chosen = a.Get("choice"); // the server names its pick
                }
                else
                {
                    var best = probs[0]; // a score has no "choice": take the most likely level
                    foreach (var kv in probs) if (kv.Value > best.Value) best = kv;
                    chosen = best.Key;
                }
                if (chosen is not string c || !labels.Contains(c))
                {
                    problems.Add($"{name}: {Py.Repr(chosen)} is not an option");
                    continue;
                }
                pick = c;
                // No usable confidence in the reply: fall back to the top probability.
                confidence = Py.IsProbability(a.Get("confidence")) ? Py.Num(a["confidence"]) : probs.Max(kv => kv.Value);
            }
            answers[name] = new Answer(pick, probs, confidence);
        }
        return (answers, problems);
    }

    /// <summary>An http(s) URL whose host is this machine: localhost, 127.0.0.0/8 or ::1.
    /// urlparse(url).hostname by hand, because System.Uri rewrites "127.1" to "127.0.0.1".</summary>
    public static bool IsLoopback(string url)
    {
        if (url.Contains('\\')) return false; // parsers disagree on what a backslash means
        url = Regex.Replace(url, "[\t\r\n]", "").TrimStart(Enumerable.Range(0, 33).Select(c => (char)c).ToArray());
        var m = Regex.Match(url, @"\A([A-Za-z][A-Za-z0-9+.\-]*)://([^/?#]*)");
        if (!m.Success || m.Groups[1].Value.ToLowerInvariant() is not ("http" or "https")) return false;
        var netloc = m.Groups[2].Value;
        if (netloc.Contains('[') != netloc.Contains(']')) return false; // urlparse raises ValueError
        var hostinfo = netloc[(netloc.LastIndexOf('@') + 1)..];
        int open = hostinfo.IndexOf('[');
        if (open >= 0)
        {
            var inside = hostinfo[(open + 1)..];
            int close = inside.IndexOf(']');
            var v6text = close >= 0 ? inside[..close] : inside;
            // urlparse accepts only an IPv6 address in brackets
            return IPAddress.TryParse(v6text, out var v6) && v6.AddressFamily == System.Net.Sockets.AddressFamily.InterNetworkV6
                   && v6.ScopeId == 0 && v6.Equals(IPAddress.IPv6Loopback);
        }
        var host = hostinfo.Split(':')[0].ToLowerInvariant();
        if (host == "localhost") return true;
        // ipaddress.ip_address takes dotted quads only, no leading zeros.
        return Regex.IsMatch(host, @"\A127\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])(\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])){2}\z");
    }

    /// <summary>A Python-parsed value as a JsonNode, to send it.</summary>
    public static JsonNode? ToJsonNode(object? v) => v switch
    {
        null => null,
        string s => JsonValue.Create(s),
        bool b => JsonValue.Create(b),
        long l => JsonValue.Create(l),
        double d => JsonValue.Create(d),
        List<object?> l => new JsonArray(l.Select(ToJsonNode).ToArray()),
        Dict d => new JsonObject(d.Items.Select(kv => new KeyValuePair<string, JsonNode?>(kv.Key, ToJsonNode(kv.Value)))),
        _ => throw new ArgumentException($"cannot send {v.GetType()}"),
    };
}

/// <summary>Sends one System One request. Stdlib only, like python/systemone.post.</summary>
public sealed class SystemOneClient
{
    private static readonly HttpClient Http = new() { Timeout = TimeSpan.FromSeconds(120) };

    /// <summary>
    /// POST one System One request; return (response, seconds). This is the whole API:
    ///
    ///     POST {base}/v1/systemone
    ///     Authorization: Bearer {TYPESAFE_API_KEY}
    ///     {"model": "jev-latest", "state": "...", "questions": {...}}
    ///
    /// There is no official C# SDK, and none is needed: HttpClient is enough.
    /// A key is only ever sent to TypeSafe or to this machine: anything else is refused,
    /// so a typo in TYPESAFE_BASE_URL cannot hand the key (or the calls) to a stranger.
    /// </summary>
    public async Task<(Dict Response, double Seconds)> PostAsync(string baseUrl, JsonObject body, string apiKey)
    {
        var root = baseUrl.TrimEnd('/');
        // The destination rule comes first, before a request object even exists.
        if (!(root == SystemOne.TypeSafeUrl || SystemOne.IsLoopback(baseUrl)))
            throw new ArgumentException($"refusing {baseUrl}: only {SystemOne.TypeSafeUrl} or a loopback address");
        using var req = new HttpRequestMessage(HttpMethod.Post, root + SystemOne.Path)
        {
            Content = new StringContent(body.ToJsonString(), Encoding.UTF8, "application/json"),
        };
        // The local adapter needs no key; TypeSafe does.
        if (apiKey.Length > 0) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
        var started = Stopwatch.StartNew();
        string text;
        try
        {
            using var resp = await Http.SendAsync(req);
            text = await resp.Content.ReadAsStringAsync();
            if (!resp.IsSuccessStatusCode)
            {
                // 401 bad key, 422 a malformed question, 429 rate limit: show what the server said.
                var detail = text.Length > 300 ? text[..300] : text;
                throw new InvalidOperationException($"HTTP {(int)resp.StatusCode} from {baseUrl}: {detail}");
            }
        }
        catch (Exception err) when (err is HttpRequestException or TaskCanceledException)
        {
            throw new InvalidOperationException($"cannot reach {baseUrl}: {err.Message}");
        }
        if (Py.Loads(text) is not Dict response) throw new InvalidOperationException($"{baseUrl}: response is not a JSON object");
        return (response, started.Elapsed.TotalSeconds);
    }
}
