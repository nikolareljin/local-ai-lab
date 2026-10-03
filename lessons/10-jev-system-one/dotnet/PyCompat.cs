// Lesson 10 - the few Python behaviours the demo's output depends on, in C#.
//
// The demo has to print exactly what python/jev.py prints and refuse exactly the
// recordings it refuses. That needs Python's float formatting (round half to even
// on the exact binary value), repr() for the llm-json error lines, json.loads
// (NaN accepted, 3 and 3.0 kept apart, dict order kept) and the canonical
// json.dumps the cassette digest is computed over.
//
// Parsed JSON: Dict (ordered), List<object?>, string, bool, null, long or
// BigInteger for an int, double for a float.

using System.Globalization;
using System.Numerics;
using System.Text;

namespace Lesson10Jev;

/// <summary>A Python dict: insertion-ordered, a repeated key keeps its first position.</summary>
public sealed class Dict
{
    private readonly List<string> _keys = new();
    private readonly Dictionary<string, object?> _values = new(StringComparer.Ordinal);

    public IReadOnlyList<string> Keys => _keys;
    public int Count => _keys.Count;
    public bool Has(string key) => _values.ContainsKey(key);
    public object? Get(string key) => _values.TryGetValue(key, out var v) ? v : null;
    public IEnumerable<KeyValuePair<string, object?>> Items => _keys.Select(k => new KeyValuePair<string, object?>(k, _values[k]));

    public object? this[string key]
    {
        get => _values[key];
        set
        {
            if (!_values.ContainsKey(key)) _keys.Add(key);
            _values[key] = value;
        }
    }
}

public sealed class JsonDecodeError : Exception
{
    public JsonDecodeError(string message) : base(message) { }
}

public static class Py
{
    public static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    // --- values ---------------------------------------------------------------
    public static bool IsNumber(object? v) => v is long or BigInteger or double or bool;

    public static double Num(object? v) => v switch
    {
        long l => l,
        BigInteger b => (double)b,
        double d => d,
        bool t => t ? 1 : 0,
        _ => throw new InvalidCastException($"not a number: {Repr(v)}"),
    };

    /// <summary>Python truthiness, for the `x or default` idioms.</summary>
    public static bool Truthy(object? v) => v switch
    {
        null => false,
        bool b => b,
        string s => s.Length > 0,
        long l => l != 0,
        BigInteger b => !b.IsZero,
        double d => d != 0,
        Dict d => d.Count > 0,
        List<object?> l => l.Count > 0,
        _ => true,
    };

    // --- strings --------------------------------------------------------------
    // str.isspace(): char.IsWhiteSpace plus \x1c-\x1f.
    private static readonly char[] Ws = (" \t\n\v\f\r\u001c\u001d\u001e\u001f\u0085\u00a0\u1680"
        + "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
        + "\u2028\u2029\u202f\u205f\u3000").ToCharArray();

    public static string Strip(string s) => s.Trim(Ws);

    /// <summary>str.lower(): U+0130 lowers to two characters in Python.</summary>
    public static string Lower(string s) => s.Replace("\u0130", "i\u0307").ToLowerInvariant();

    /// <summary>len() counts code points, not UTF-16 units.</summary>
    public static int Len(string s) => s.EnumerateRunes().Count();
    public static string Ljust(string s, int w) => s + new string(' ', Math.Max(0, w - Len(s)));
    public static string Rjust(string s, int w) => new string(' ', Math.Max(0, w - Len(s))) + s;

    // --- floats ---------------------------------------------------------------
    /// <summary>f"{x:.{d}f}": the exact binary value, rounded half to even.</summary>
    public static string Fixed(double x, int d)
    {
        if (double.IsNaN(x)) return "nan";
        if (double.IsInfinity(x)) return x > 0 ? "inf" : "-inf";
        long bits = BitConverter.DoubleToInt64Bits(x);
        bool neg = bits < 0;
        int e = (int)((bits >> 52) & 0x7ff);
        BigInteger mant = bits & 0xfffffffffffffL;
        int exp = -1074;
        if (e != 0)
        {
            mant |= BigInteger.One << 52;
            exp = e - 1075;
        }
        // value = numer / 10^k, exactly
        BigInteger numer;
        int k;
        if (exp >= 0)
        {
            numer = mant << exp;
            k = 0;
        }
        else
        {
            k = -exp;
            numer = mant * BigInteger.Pow(5, k);
        }
        BigInteger q;
        if (k <= d)
        {
            q = numer * BigInteger.Pow(10, d - k);
        }
        else
        {
            var den = BigInteger.Pow(10, k - d);
            q = BigInteger.DivRem(numer, den, out var rem);
            var r2 = rem * 2;
            if (r2 > den || (r2 == den && !q.IsEven)) q += 1;
        }
        var s = q.ToString(Inv).PadLeft(d + 1, '0');
        return (neg ? "-" : "") + (d > 0 ? s[..^d] + "." + s[^d..] : s);
    }

    /// <summary>round(x) to an int: half to even.</summary>
    public static long RoundEven(double x) => (long)Math.Round(x, MidpointRounding.ToEven);

    /// <summary>repr(float): shortest round-trip digits in Python's layout.</summary>
    public static string FloatRepr(double x)
    {
        if (double.IsNaN(x)) return "nan";
        if (double.IsInfinity(x)) return x > 0 ? "inf" : "-inf";
        if (x == 0) return BitConverter.DoubleToInt64Bits(x) < 0 ? "-0.0" : "0.0";
        var r = Math.Abs(x).ToString("R", Inv);
        int ePos = r.IndexOf('E');
        int exp10 = ePos >= 0 ? int.Parse(r[(ePos + 1)..], Inv) : 0;
        var mant = ePos >= 0 ? r[..ePos] : r;
        int dot = mant.IndexOf('.');
        var intPart = dot >= 0 ? mant[..dot] : mant;
        var all = intPart + (dot >= 0 ? mant[(dot + 1)..] : "");
        int lz = all.Length - all.TrimStart('0').Length;
        var digits = all.Trim('0');
        int e = intPart.Length - 1 - lz + exp10;
        var sign = x < 0 ? "-" : "";
        if (e >= -4 && e < 16)
        {
            if (e >= 0)
            {
                var whole = digits.Length > e + 1 ? digits[..(e + 1)] : digits.PadRight(e + 1, '0');
                var frac = digits.Length > e + 1 ? digits[(e + 1)..] : "0";
                return $"{sign}{whole}.{frac}";
            }
            return $"{sign}0.{new string('0', -e - 1)}{digits}";
        }
        var m = digits[0] + (digits.Length > 1 ? "." + digits[1..] : "");
        return $"{sign}{m}e{(e < 0 ? "-" : "+")}{Math.Abs(e).ToString(Inv).PadLeft(2, '0')}";
    }

    /// <summary>systemone.fsum: every value as a float, Neumaier compensation from the first.</summary>
    public static double FSum(IEnumerable<object?> values)
    {
        double total = 0.0, comp = 0.0;
        foreach (var raw in values)
        {
            double v = Num(raw);
            double t = total + v;
            comp += Math.Abs(total) >= Math.Abs(v) ? (total - t) + v : (v - t) + total;
            total = t;
        }
        return total + comp;
    }

    /// <summary>A real number in [0, 1]. Not a bool, not NaN, not 1.5.</summary>
    public static bool IsProbability(object? v) =>
        v is long or BigInteger or double && double.IsFinite(Num(v)) && Num(v) >= 0 && Num(v) <= 1;

    /// <summary>sum() as CPython 3.12+ does it: ints added exactly until the first float,
    /// then floats with Neumaier compensation (ints after that added plainly).</summary>
    public static object PySum(IEnumerable<object?> values)
    {
        using var it = values.GetEnumerator();
        BigInteger ints = 0;
        double f = 0, c = 0;
        bool inFloats = false;
        while (it.MoveNext())
        {
            var v = it.Current;
            if (!inFloats)
            {
                if (v is double first)
                {
                    f = (double)ints + first;
                    inFloats = true;
                }
                else ints += v switch { long l => l, BigInteger b => b, bool t => t ? 1 : 0, _ => throw new InvalidCastException($"sum(): {Repr(v)}") };
                continue;
            }
            if (v is not double x)
            {
                f += Num(v);
                continue;
            }
            double sum = f + x;
            c += Math.Abs(f) >= Math.Abs(x) ? (f - sum) + x : (x - sum) + f;
            f = sum;
        }
        if (!inFloats) return ints >= long.MinValue && ints <= long.MaxValue ? (object)(long)ints : ints;
        return c != 0 && double.IsFinite(c) ? f + c : f;
    }

    // --- repr() ---------------------------------------------------------------
    private static bool Printable(Rune r)
    {
        if (r.Value == ' ') return true;
        return Rune.GetUnicodeCategory(r) switch
        {
            UnicodeCategory.Control or UnicodeCategory.Format or UnicodeCategory.Surrogate
                or UnicodeCategory.PrivateUse or UnicodeCategory.OtherNotAssigned
                or UnicodeCategory.LineSeparator or UnicodeCategory.ParagraphSeparator
                or UnicodeCategory.SpaceSeparator => false,
            _ => true,
        };
    }

    private static string ReprStr(string s)
    {
        char q = s.Contains('\'') && !s.Contains('"') ? '"' : '\'';
        var sb = new StringBuilder().Append(q);
        foreach (var r in s.EnumerateRunes())
        {
            int cp = r.Value;
            if (cp == q || cp == '\\') sb.Append('\\').Append((char)cp);
            else if (cp == '\n') sb.Append("\\n");
            else if (cp == '\r') sb.Append("\\r");
            else if (cp == '\t') sb.Append("\\t");
            else if (cp < 0x20 || cp == 0x7f) sb.Append("\\x").Append(cp.ToString("x2", Inv));
            else if (cp < 0x7f || Printable(r)) sb.Append(r.ToString());
            else if (cp <= 0xff) sb.Append("\\x").Append(cp.ToString("x2", Inv));
            else if (cp <= 0xffff) sb.Append("\\u").Append(cp.ToString("x4", Inv));
            else sb.Append("\\U").Append(cp.ToString("x8", Inv));
        }
        return sb.Append(q).ToString();
    }

    public static string Repr(object? v) => v switch
    {
        null => "None",
        string s => ReprStr(s),
        bool b => b ? "True" : "False",
        long l => l.ToString(Inv),
        BigInteger b => b.ToString(Inv),
        double d => FloatRepr(d),
        List<object?> l => "[" + string.Join(", ", l.Select(Repr)) + "]",
        IEnumerable<string> l => "[" + string.Join(", ", l.Select(Repr)) + "]",
        Dict d => "{" + string.Join(", ", d.Items.Select(kv => Repr(kv.Key) + ": " + Repr(kv.Value))) + "}",
        _ => throw new ArgumentException($"repr(): unsupported {v.GetType()}"),
    };

    // --- json -----------------------------------------------------------------
    /// <summary>json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    /// for strings, ints, bools, None, lists and dicts - what a digest is taken over.</summary>
    public static string Canonical(object? v) => v switch
    {
        null => "null",
        string s => DumpStr(s),
        bool b => b ? "true" : "false",
        long l => l.ToString(Inv),
        BigInteger b => b.ToString(Inv),
        List<object?> l => "[" + string.Join(",", l.Select(Canonical)) + "]",
        Dict d => "{" + string.Join(",", d.Keys.OrderBy(k => k, CodePointComparer.Instance)
            .Select(k => DumpStr(k) + ":" + Canonical(d[k]))) + "}",
        _ => throw new ArgumentException($"canonical(): unsupported {v.GetType()}"),
    };

    private static string DumpStr(string s)
    {
        var sb = new StringBuilder("\"");
        foreach (char c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                default:
                    if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4", Inv));
                    else sb.Append(c);
                    break;
            }
        }
        return sb.Append('"').ToString();
    }

    private sealed class CodePointComparer : IComparer<string>
    {
        public static readonly CodePointComparer Instance = new();
        public int Compare(string? a, string? b)
        {
            var x = a!.EnumerateRunes().GetEnumerator();
            var y = b!.EnumerateRunes().GetEnumerator();
            while (true)
            {
                bool hx = x.MoveNext(), hy = y.MoveNext();
                if (!hx || !hy) return hx == hy ? 0 : (hx ? 1 : -1);
                int d = x.Current.Value - y.Current.Value;
                if (d != 0) return d;
            }
        }
    }

    /// <summary>json.loads: NaN/Infinity accepted, control characters in strings refused.</summary>
    public static object? Loads(string text)
    {
        int i = 0;
        void Fail(string msg) => throw new JsonDecodeError($"{msg}: char {i}");
        void Skip()
        {
            while (i < text.Length && " \t\n\r".Contains(text[i])) i++;
        }

        object? Value()
        {
            if (i >= text.Length) Fail("Expecting value");
            char c = text[i];
            if (c == '"') return Str();
            if (c == '{') return Obj();
            if (c == '[') return Arr();
            foreach (var (word, v) in new (string, object?)[] { ("null", null), ("true", true), ("false", false),
                         ("NaN", double.NaN), ("Infinity", double.PositiveInfinity), ("-Infinity", double.NegativeInfinity) })
            {
                if (string.CompareOrdinal(text, i, word, 0, word.Length) == 0)
                {
                    i += word.Length;
                    return v;
                }
            }
            var m = System.Text.RegularExpressions.Regex.Match(text[i..], @"\A-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?");
            if (!m.Success) Fail("Expecting value");
            i += m.Length;
            if (m.Groups[1].Success || m.Groups[2].Success) return double.Parse(m.Value, Inv);
            var big = BigInteger.Parse(m.Value, Inv);
            return big >= long.MinValue && big <= long.MaxValue ? (object)(long)big : big;
        }

        string Str()
        {
            i++;
            var sb = new StringBuilder();
            while (true)
            {
                if (i >= text.Length) Fail("Unterminated string starting at");
                char c = text[i++];
                if (c == '"') return sb.ToString();
                if (c < ' ') Fail("Invalid control character at");
                if (c != '\\')
                {
                    sb.Append(c);
                    continue;
                }
                char e = i < text.Length ? text[i++] : '\0';
                switch (e)
                {
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'u' when i + 4 <= text.Length && int.TryParse(text.AsSpan(i, 4), NumberStyles.AllowHexSpecifier, Inv, out var code):
                        sb.Append((char)code);
                        i += 4;
                        break;
                    default: Fail("Invalid \\escape"); break;
                }
            }
        }

        List<object?> Arr()
        {
            i++;
            var list = new List<object?>();
            Skip();
            if (i < text.Length && text[i] == ']')
            {
                i++;
                return list;
            }
            while (true)
            {
                Skip();
                list.Add(Value());
                Skip();
                if (i < text.Length && text[i] == ',') i++;
                else if (i < text.Length && text[i] == ']')
                {
                    i++;
                    return list;
                }
                else Fail("Expecting ',' delimiter");
            }
        }

        Dict Obj()
        {
            i++;
            var d = new Dict();
            Skip();
            if (i < text.Length && text[i] == '}')
            {
                i++;
                return d;
            }
            while (true)
            {
                Skip();
                if (i >= text.Length || text[i] != '"') Fail("Expecting property name enclosed in double quotes");
                var key = Str();
                Skip();
                if (i >= text.Length || text[i++] != ':') Fail("Expecting ':' delimiter");
                Skip();
                d[key] = Value();
                Skip();
                if (i < text.Length && text[i] == ',') i++;
                else if (i < text.Length && text[i] == '}')
                {
                    i++;
                    return d;
                }
                else Fail("Expecting ',' delimiter");
            }
        }

        Skip();
        var result = Value();
        Skip();
        if (i != text.Length) Fail("Extra data");
        return result;
    }
}
