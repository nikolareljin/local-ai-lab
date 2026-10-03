// Lesson 10 - Jev and System One models vs a local LLM, on two fake call centers.
// C# port of python/jev.py: `demo` prints byte for byte what Python prints, and
// `ask` sends one call to a System One server, like `jev.py ask --backend typesafe`.
//
//     dotnet run --project dotnet -c Release --nologo [-- demo] [-- --dataset media]
//     dotnet run --project dotnet -c Release --nologo -- ask "Caller: my car was stolen"

using System.Text;
using System.Text.Json.Nodes;
using Lesson10Jev;

using Run = (System.Collections.Generic.Dictionary<string, Lesson10Jev.Answer> Answers, double Seconds, long Calls, System.Collections.Generic.List<string> Problems);

var stdout = new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { NewLine = "\n" };
var stderr = new StreamWriter(Console.OpenStandardError(), new UTF8Encoding(false)) { NewLine = "\n", AutoFlush = true };
Console.OutputEncoding = new UTF8Encoding(false);
try
{
    return await Jev.Cli(args, stdout, stderr);
}
catch (Jev.StaleCassette err)
{
    stdout.Flush();
    stderr.WriteLine($"StaleCassette: {err.Message}");
    return 1;
}
catch (Jev.Exit err)
{
    stdout.Flush();
    stderr.WriteLine(err.Message);
    return err.Code;
}
finally
{
    stdout.Flush();
}

static class Jev
{
    public sealed class StaleCassette(string message) : Exception(message);
    public sealed class Exit(int code, string message) : Exception(message)
    {
        public int Code { get; } = code;
    }

    static readonly string Data = Environment.GetEnvironmentVariable("LESSON10_DATA_DIR") is { Length: > 0 } d
        ? Path.GetFullPath(d)  // port-only test hook (Python has none): an edited copy of data/
        : Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "data"));
    static readonly string Cassettes = Path.Combine(Data, "cassettes");

    // What the demo replays, in the order the scorecard prints them.
    static readonly (string Backend, string Model)[] RecordedModels =
    {
        ("llm-json", "qwen3:1.7b"),
        ("local", "qwen3:1.7b"),
        ("local", "qwen3.5:4b"),
        ("typesafe", "jev-latest"),
    };

    const string DefaultDataset = "insurance";

    /// <summary>jev-like-qwen3-1.7b-insurance.json: engine, model and dataset.</summary>
    static string CassetteName(string backend, string model, string dataset = DefaultDataset) => backend == "typesafe"
        ? $"typesafe-jev-{dataset}.json"
        : $"{(backend == "llm-json" ? "llm-json" : "jev-like")}-{model.Replace(':', '-').Replace('/', '-')}-{dataset}.json";

    static string Read(string path) => File.ReadAllText(path, new UTF8Encoding(false));

    // Per dataset: title and the short column name of each question.
    static readonly Dict Datasets = (Dict)Py.Loads(Read(Path.Combine(Data, "datasets.json")))!;

    static (Dict Questions, List<Dict> Records) LoadDataset(string name)
    {
        var questions = (Dict)((Dict)Py.Loads(Read(Path.Combine(Data, "questions.json")))!)[name]!;
        var records = System.Text.RegularExpressions.Regex.Split(Read(Path.Combine(Data, $"{name}.jsonl")), "\r\n|\r|\n")
            .Where(line => Py.Strip(line).Length > 0).Select(line => (Dict)Py.Loads(line)!).ToList();
        return (questions, records);
    }

    static string S(Dict d, string key) => (string)d[key]!;

    // ----------------------------------------------------------------------- engines.py
    // data/rules.json: per dataset and question, an ordered list of [label, [words]].
    // The first rule with a word in the transcript wins; the last rule is the default.
    static readonly Dict Rules = (Dict)Py.Loads(Read(Path.Combine(Data, "rules.json")))!;

    static string RulePick(string text, List<object?> rules)
    {
        var low = Py.Lower(text);
        foreach (var rule in rules.Cast<List<object?>>())
            if (((List<object?>)rule[1]!).Any(w => low.Contains((string)w!, StringComparison.Ordinal))) return (string)rule[0]!;
        return (string)((List<object?>)rules[^1]!)[0]!;
    }

    /// <summary>A System One answer that puts all probability on one label.</summary>
    static Dict Certain(Dict q, string pick)
    {
        var labels = SystemOne.Options(q);
        if (S(q, "type") == "noul") return new Dict { ["type"] = "noul", ["noul"] = pick == "yes" ? 1.0 : 0.0 };
        var probs = new Dict();
        for (int i = 0; i < labels.Count; i++) probs[S(q, "type") == "choice" ? labels[i] : i.ToString(Py.Inv)] = labels[i] == pick ? 1.0 : 0.0;
        if (S(q, "type") == "choice")
            return new Dict { ["type"] = "choice", ["choice"] = pick, ["confidence"] = 1.0, ["probabilities"] = probs };
        var legend = new Dict();
        for (int i = 0; i < labels.Count; i++) legend[i.ToString(Py.Inv)] = labels[i];
        return new Dict { ["type"] = "score", ["score"] = (double)labels.IndexOf(pick), ["confidence"] = 1.0,
                          ["legend"] = legend, ["probabilities"] = probs };
    }

    /// <summary>Answer by keyword. A question with no rules gets its first option.</summary>
    static Dict KeywordsResponse(Dict body, string dataset = DefaultDataset)
    {
        var rules = (Dict)Rules[dataset]!;
        var state = body["state"] as string ?? Py.Repr(body["state"]);
        var answers = new Dict();
        foreach (var (name, value) in ((Dict)body["questions"]!).Items)
        {
            var q = (Dict)value!;
            var pick = rules.Has(name) ? RulePick(state, (List<object?>)rules[name]!) : SystemOne.Options(q)[0];
            answers[name] = Certain(q, pick);
        }
        return new Dict { ["model"] = "keywords", ["answers"] = answers, ["usage"] = new Dict() };
    }

    /// <summary>Read what the model wrote. Anything that is not a valid option is a type error.</summary>
    static (Dict Response, List<string> Errors) ParseLlmJson(Dict questions, string text)
    {
        var errors = new List<string>();
        var match = System.Text.RegularExpressions.Regex.Match(text, @"\{.*\}", System.Text.RegularExpressions.RegexOptions.Singleline);
        object? written;
        try
        {
            written = match.Success ? Py.Loads(match.Value) : null;
        }
        catch (JsonDecodeError)
        {
            written = null;
        }
        if (written is not Dict w)
            return (new Dict { ["model"] = "llm-json", ["answers"] = new Dict(), ["usage"] = new Dict() }, new() { "not a JSON object" });
        var answers = new Dict();
        foreach (var (name, qv) in questions.Items)
        {
            var q = (Dict)qv!;
            var value = w.Get(name);
            if (value is bool b) value = b ? "yes" : "no"; // {"refund_request": true} is a fair reading
            if (value is not string s || !SystemOne.Options(q).Contains(Py.Lower(Py.Strip(s))))
            {
                errors.Add($"{name}={Py.Repr(value)}");
                continue;
            }
            answers[name] = Certain(q, Py.Lower(Py.Strip(s)));
        }
        return (new Dict { ["model"] = "llm-json", ["answers"] = answers, ["usage"] = new Dict() }, errors);
    }

    // ----------------------------------------------------------------------- policy.py
    // The model answers questions; this code decides. The thresholds are the knobs.
    const double Emergency = 0.5;  // P(someone needs help right now) to dispatch assistance
    const double Siu = 0.6;        // P(fraud signals) to send a claim to the Special Investigations Unit
    const double FastTrack = 0.8;  // P(no fraud signals) needed to pay a small claim without a human
    const double Confident = 0.6;  // below this confidence in the caller's intent, a person takes the call
    const double Retain = 0.5;     // P(high churn risk) to hand the call to the retention desk
    const double Refund = 0.8;     // P(wants money back) to draft a refund for approval

    static double Prob(Dictionary<string, Answer> answers, string name, string label, double fallback = 0.0) =>
        answers.TryGetValue(name, out var a) ? a.Prob(label, fallback) : fallback;

    /// <summary>One action per insurance call, from the answers to the six questions.</summary>
    static string Decide(Dictionary<string, Answer> answers, double siu = Siu)
    {
        answers.TryGetValue("intent", out var intent);
        if (Prob(answers, "emergency", "yes") >= Emergency) return "dispatch emergency help"; // first, whatever else
        if (intent is null || intent.Confidence < Confident) return "human agent"; // never guess
        if (intent.Pick is "complaint" or "cancel_policy") return "human agent";
        if (intent.Pick is "claim_status" or "coverage_question") return "self-service answer";
        // a new claim
        double pFraud = Prob(answers, "fraud_signals", "yes", 1.0);
        if (pFraud >= siu) return "special investigations";
        bool small = Prob(answers, "severity", "none") + Prob(answers, "severity", "minor") >= 0.5;
        if (small && Prob(answers, "needs_adjuster", "yes", 1.0) < 0.5 && 1 - pFraud >= FastTrack) return "fast-track payout";
        return "assign adjuster";
    }

    /// <summary>One action per newspaper call.</summary>
    static string DecideMedia(Dictionary<string, Answer> answers, double retain = Retain)
    {
        if (!answers.TryGetValue("topic", out var topic)) return "human agent";
        if (topic.Pick == "editorial") return "pass to newsroom";
        if (topic.Pick == "advertising") return "pass to ad sales";
        if (topic.Pick == "cancel" || Prob(answers, "churn_risk", "high", 1.0) >= retain) return "retention desk";
        if (Prob(answers, "wants_refund", "yes", 1.0) >= Refund) return "refund for approval";
        return "self-service answer";
    }

    /// <summary>What the scorecard needs to know about each policy. Decide takes the answers and
    /// an optional value for the threshold the demo sweeps (Knob); Watch is the action it controls.</summary>
    sealed record Policy(Func<Dictionary<string, Answer>, double?, string> Decide, string Knob, double[] Values,
                         string Watch, string Wrong, string Missed);

    static readonly Dictionary<string, Policy> Policies = new()
    {
        ["insurance"] = new((a, knob) => Decide(a, knob ?? Siu), "siu", new[] { 0.3, 0.6, 0.9 }, "special investigations",
                            "honest callers investigated", "suspicious claims not investigated"),
        ["media"] = new((a, knob) => DecideMedia(a, knob ?? Retain), "retain", new[] { 0.3, 0.5, 0.9 }, "retention desk",
                        "happy readers sent to retention", "leaving readers not sent to retention"),
    };

    // ----------------------------------------------------------------------- scorecard.py
    static Dictionary<string, Answer> GoldAnswers(Dict questions, Dict labels)
    {
        var outp = new Dictionary<string, Answer>();
        foreach (var (name, qv) in questions.Items)
        {
            var truth = S(labels, name);
            var probs = SystemOne.Options((Dict)qv!).Select(l => new KeyValuePair<string, double>(l, l == truth ? 1.0 : 0.0)).ToList();
            outp[name] = new Answer(truth, probs, 1.0);
        }
        return outp;
    }

    static double Brier(Dict q, Answer? answer, string truth)
    {
        var labels = SystemOne.Options(q);
        return Py.FSum(labels.Select(label =>
        {
            double p = answer is null ? 1.0 / labels.Count : answer.Prob(label, double.NaN);
            double d = p - (label == truth ? 1.0 : 0.0);
            return (object?)(d * d);
        }));
    }

    sealed record Score(int N, Dictionary<string, int> Correct, int Typed, int Asked, double Brier,
                        int Actions, int Wrong, int Missed, double Seconds, long Calls);

    /// <summary>`knob` overrides the policy's main threshold, for the engine and the labels alike.</summary>
    static Score ScoreRuns(Dict questions, List<Dict> records, Dictionary<string, Run> runs, Policy pol, double? knob = null)
    {
        int n = records.Count;
        var correct = questions.Keys.ToDictionary(k => k, _ => 0);
        int typed = 0, actions = 0, wrong = 0, missed = 0;
        double brierSum = 0.0;
        var seconds = new List<double>();
        foreach (var rec in records)
        {
            var run = runs[S(rec, "id")];
            var labels = (Dict)rec["labels"]!;
            foreach (var (name, qv) in questions.Items)
            {
                run.Answers.TryGetValue(name, out var a);
                if (a is not null) typed++;
                if (a is not null && a.Pick == S(labels, name)) correct[name]++;
                brierSum += Brier((Dict)qv!, a, S(labels, name));
            }
            var got = pol.Decide(run.Answers, knob);
            var want = pol.Decide(GoldAnswers(questions, labels), knob);
            if (got == want) actions++;
            if (got == pol.Watch && want != pol.Watch) wrong++;
            if (want == pol.Watch && got != pol.Watch) missed++;
            seconds.Add(run.Seconds);
        }
        return new Score(n, correct, typed, n * questions.Count, brierSum / (n * questions.Count), actions, wrong, missed,
                         seconds.Count > 0 ? Median(seconds) : 0.0, n > 0 ? runs[S(records[0], "id")].Calls : 0);
    }

    static double Median(List<double> xs)
    {
        var s = xs.OrderBy(x => x).ToList();
        int i = s.Count / 2;
        return s.Count % 2 == 1 ? s[i] : (s[i - 1] + s[i]) / 2;
    }

    // ----------------------------------------------------------------------- jev.py
    static Run ToRun(Dict questions, Dict stored)
    {
        object? response;
        List<string> problems;
        if (stored.Has("text")) (response, problems) = ParseLlmJson(questions, S(stored, "text"));
        else (response, problems) = (stored["response"], new List<string>());
        var (answers, more) = SystemOne.ReadAnswers(questions, response);
        return (answers, Py.Num(stored["seconds"]), Convert.ToInt64(stored["calls"]), problems.Concat(more).ToList());
    }

    static Dict? LoadCassette(string file, Dict questions, List<Dict> records, string dataset)
    {
        var path = Path.Combine(Cassettes, file);
        if (!File.Exists(path)) return null;
        var tape = (Dict)Py.Loads(Read(path))!;
        if (tape.Get("dataset") as string != dataset) return null;
        // prompt_version is not checked here; Python's test suite enforces it.
        var calls = (Dict)tape["calls"]!;
        foreach (var rec in records)
        {
            if (calls.Get(S(rec, "id")) is not Dict stored)
                throw new StaleCassette($"{file}: has no recording of {S(rec, "id")} - re-record it without --limit");
            var want = SystemOne.Digest(SystemOne.BuildRequest(rec["text"], questions, (string)tape["model"]!));
            if (stored.Get("digest") as string != want)
                throw new StaleCassette($"{file}: {S(rec, "id")} was recorded for a different question or text - re-record it");
        }
        return tape;
    }

    // "jev-like 4b": the engine and the model's size tag, for narrow columns.
    static string ShortName(string backend, Dict? tape)
    {
        if (tape is null) return backend;
        var prefix = backend switch { "llm-json" => "llm-json", "local" => "jev-like", _ => "typesafe" };
        var model = S(tape, "model");
        return $"{prefix} {model[(model.LastIndexOf(':') + 1)..]}";
    }

    static string LabelFor(string backend, Dict? tape, string model = "")
    {
        if (backend == "keywords") return "keywords (rules)";
        var name = tape is not null ? S(tape, "model") : model;
        return backend switch
        {
            "llm-json" => $"LLM writes JSON ({name})",
            "local" => $"Jev-like adapter ({(name.StartsWith("local-", StringComparison.Ordinal) ? name[6..] : name)})",
            _ => $"TypeSafe Jev ({name})",
        };
    }

    static string I(long v) => v.ToString(Py.Inv);

    static string FmtRow(string label, Score s, Dict questions)
    {
        var cells = questions.Keys.Select(q => $"{Py.Rjust(I(s.Correct[q]), 2)}/{s.N}");
        return Py.Ljust(label, 32) + string.Concat(cells.Select(c => Py.Rjust(c, 7)))
            + Py.Rjust(I(s.Typed * 100L / s.Asked), 6) + "%" + Py.Rjust(Py.Fixed(s.Brier, 3), 7)
            + Py.Rjust(I(s.Actions), 5) + $"/{s.N}" + Py.Rjust(I(s.Wrong), 6) + Py.Rjust(I(s.Missed), 7)
            + Py.Rjust(Py.Fixed(s.Seconds, 1), 8) + Py.Rjust(I(s.Calls), 6);
    }

    static string Header(Dict questions, string dataset)
    {
        var shortNames = (Dict)((Dict)Datasets[dataset]!)["short"]!;
        var cols = string.Concat(questions.Keys.Select(q => Py.Rjust(S(shortNames, q), 7)));
        return Py.Ljust("engine", 32) + cols + Py.Rjust("typed", 7) + Py.Rjust("brier", 7) + Py.Rjust("action", 8)
            + Py.Rjust("wrong", 6) + Py.Rjust("missed", 7) + Py.Rjust("s/call", 8) + Py.Rjust("calls", 6);
    }

    static int Demo(string dataset, TextWriter output)
    {
        var (questions, records) = LoadDataset(dataset);
        var pol = Policies[dataset];
        var meta = (Dict)Datasets[dataset]!;
        void P(string line = "") => output.WriteLine(line);
        P($"Lesson 10 \u00b7 Jev and System One models - {S(meta, "title")}: {records.Count} labelled fake "
          + $"calls, {questions.Count} typed questions");
        P("Replayed from recorded replies: no model, no network. "
          + "Live: ./run -l 10 live --backend keywords,llm-json,local");
        P();
        P(Header(questions, dataset));
        var keywordRuns = new Dictionary<string, Run>();
        foreach (var r in records)
        {
            var response = KeywordsResponse(SystemOne.BuildRequest(r["text"], questions), dataset);
            keywordRuns[S(r, "id")] = ToRun(questions, new Dict { ["response"] = response, ["seconds"] = 0.0, ["calls"] = 0L });
        }
        var rows = new List<(string Backend, Dict? Tape, Dictionary<string, Run> Runs)> { ("keywords", null, keywordRuns) };
        var missing = new List<(string Backend, string Model)>();
        foreach (var (backend, model) in RecordedModels)
        {
            var tape = LoadCassette(CassetteName(backend, model, dataset), questions, records, dataset);
            if (tape is null)
            {
                missing.Add((backend, model));
                continue;
            }
            var calls = (Dict)tape["calls"]!;
            rows.Add((backend, tape, records.ToDictionary(r => S(r, "id"), r => ToRun(questions, (Dict)calls[S(r, "id")]!))));
        }
        foreach (var (backend, tape, runs) in rows)
            P(FmtRow(LabelFor(backend, tape), ScoreRuns(questions, records, runs, pol), questions));
        foreach (var (backend, model) in missing)
        {
            var hint = backend == "typesafe" ? "needs TYPESAFE_API_KEY: ./run -l 10 record --backend typesafe"
                : $"./run -l 10 record --backend {backend} --model {model}";
            hint += dataset == DefaultDataset ? "" : $" --dataset {dataset}";
            P($"{Py.Ljust(LabelFor(backend, null, model), 32)}not recorded - {hint}");
        }
        P();
        P("Columns: right/total per question; typed = answers that were a valid option;");
        P("brier = probability error, 0 best, 2 = certain and wrong; action = same action as the");
        P($"human labels lead to; wrong = {pol.Wrong}; missed = {pol.Missed};");
        P("s/call = median seconds; calls = model calls per record.");

        P();
        P("The traps - the action each engine's answers lead to:");
        foreach (var r in records.Where(rec => Py.Truthy(rec["trap"])))
        {
            var want = pol.Decide(GoldAnswers(questions, (Dict)r["labels"]!), null);
            P($"  {S(r, "id")}  {S(r, "trap")}");
            P($"    {Py.Ljust("labels", 14)} {want}");
            foreach (var (backend, tape, runs) in rows)
            {
                var got = pol.Decide(runs[S(r, "id")].Answers, null);
                P($"    {Py.Ljust(ShortName(backend, tape), 14)} {got}{(got == want ? "" : "   <- wrong")}");
            }
        }

        var name = pol.Knob.ToUpperInvariant();
        P();
        P($"The threshold is a business decision. '{pol.Watch}' as {name} moves:");
        P($"  {Py.Ljust("engine", 32)}" + string.Concat(pol.Values.Select(t => Py.Rjust($"{name} {Py.Fixed(t, 1)}", 20))));
        foreach (var (backend, tape, runs) in rows)
        {
            var cells = pol.Values.Select(t =>
            {
                var s = ScoreRuns(questions, records, runs, pol, t);
                return $"{s.Wrong} wrong {s.Missed} missed";
            });
            P($"  {Py.Ljust(LabelFor(backend, tape), 32)}" + string.Concat(cells.Select(c => Py.Rjust(c, 20))));
        }
        P("  Rules and JSON answers are always 0 or 1, so the knob does nothing for them.");
        return 0;
    }

    /// <summary>One call to a System One server: TypeSafe's Jev, or the adapter on loopback.</summary>
    static async Task<int> Ask(string text, string dataset, TextWriter output)
    {
        var (questions, _) = LoadDataset(dataset);
        var model = Environment.GetEnvironmentVariable("TYPESAFE_DEFAULT_MODEL") is { Length: > 0 } m ? m : "jev-latest";
        var url = Environment.GetEnvironmentVariable("TYPESAFE_BASE_URL") ?? SystemOne.TypeSafeUrl;
        var key = Environment.GetEnvironmentVariable("TYPESAFE_API_KEY") ?? "";
        if (key.Length == 0 && !SystemOne.IsLoopback(url))
            throw new Exit(1, "TYPESAFE_API_KEY is not set (get one at https://console.typesafe.ai)");
        var body = SystemOne.BuildRequest(text, questions, model);
        Dict response;
        double seconds;
        try
        {
            (response, seconds) = await new SystemOneClient().PostAsync(url, (JsonObject)SystemOne.ToJsonNode(body)!, key);
        }
        catch (Exception err) when (err is ArgumentException or InvalidOperationException or JsonDecodeError)
        {
            throw new Exit(1, err.Message);
        }
        var run = ToRun(questions, new Dict { ["response"] = response, ["seconds"] = seconds, ["calls"] = 1L });
        output.WriteLine($"{LabelFor("typesafe", null, model)}  {Py.Fixed(run.Seconds, 1)}s, {run.Calls} model call(s)");
        foreach (var name in questions.Keys)
        {
            if (!run.Answers.TryGetValue(name, out var a))
            {
                output.WriteLine($"  {Py.Ljust(name, 15)} (no valid answer)");
                continue;
            }
            var probs = string.Join("  ", a.Probs.Select(kv => $"{kv.Key} {Py.Fixed(kv.Value, 2)}"));
            output.WriteLine($"  {Py.Ljust(name, 15)} {a.Pick}");
            output.WriteLine($"      {probs}");
        }
        foreach (var problem in run.Problems) output.WriteLine($"  ! {problem}");
        output.WriteLine($"  -> action: {Policies[dataset].Decide(run.Answers, null)}");
        return 0;
    }

    public static async Task<int> Cli(string[] args, TextWriter output, TextWriter errors)
    {
        var names = Datasets.Keys;
        var usage = $"usage: Lesson10Jev [demo] [--dataset {{{string.Join(",", names)}}}] | ask TEXT [--dataset ...]";
        // .NET 8 `dotnet run` forwards --nologo (and a literal "--") to the program; drop them.
        var rest = args.Where(a => a is not ("--nologo" or "--")).ToList();
        bool ask = rest.Count > 0 && rest[0] == "ask";
        if (rest.Count > 0 && rest[0] is "ask" or "demo") rest.RemoveAt(0);
        var dataset = DefaultDataset;
        string? text = null;
        for (int i = 0; i < rest.Count; i++)
        {
            string? v;
            if (rest[i] == "--dataset") v = i + 1 < rest.Count ? rest[++i] : null;
            else if (rest[i].StartsWith("--dataset=", StringComparison.Ordinal)) v = rest[i][10..];
            else if (ask && text is null && !rest[i].StartsWith("--", StringComparison.Ordinal))
            {
                text = rest[i];
                continue;
            }
            else throw new Exit(2, $"{usage}\nerror: unrecognized arguments: {rest[i]}");
            if (v is null || !names.Contains(v))
                throw new Exit(2, $"{usage}\nerror: argument --dataset: invalid choice: {Py.Repr(v ?? "")}");
            dataset = v;
        }
        if (!ask) return Demo(dataset, output);
        if (text is null) throw new Exit(2, usage + "\nerror: ask takes exactly one TEXT argument");
        return await Ask(text, dataset, output);
    }
}
