// Lesson 9 - the few Python behaviours the demo's output depends on, in Node.
//
// The demo replays recorded model turns, and each turn carries a digest of the
// exact conversation (see cassette.mjs). The digest is a sha256 over Python's
// json.dumps, so to verify it Node has to produce the same bytes: the same JSON
// separators, the same float formatting, and the same idea of int versus float.
// The printed output uses Python's repr() of arguments and its rounding rules.
// None of that is exotic, but none of it is what JavaScript does by default.
//
// Numbers: JSON.parse turns 3 and 3.0 into the same value, Python does not, and
// the difference reaches both the validator ("integer") and the digest ("3.0").
// So JSON is parsed here: an int stays a JS number (a BigInt past 2^53), a float
// becomes a PyFloat. Every other module treats a plain JS number as a Python int
// unless it is non-integral.
//
// Known gap: a JS object puts integer-like keys ("1", "42") first, a Python dict
// keeps insertion order. Tool arguments with such keys would print and validate
// in a different order. No schema here has one.

// --- values -------------------------------------------------------------------

export class PyFloat {
  constructor(value) {
    this.value = value;
  }
}

/** A JSON number (int, BigInt or PyFloat) as a JS number, for arithmetic. */
export function num(v) {
  if (v instanceof PyFloat) return v.value;
  if (typeof v === "bigint") return Number(v);
  return v;
}

export const isPyFloat = (v) => v instanceof PyFloat || (typeof v === "number" && !Number.isInteger(v));
export const isPyInt = (v) => typeof v === "bigint" || (typeof v === "number" && Number.isInteger(v));
export const isDict = (v) =>
  v !== null && typeof v === "object" && !Array.isArray(v) && !(v instanceof PyFloat);

/** Python truthiness, for the `x or default` idioms the Python code leans on. */
export function truthy(v) {
  if (v === null || v === undefined || v === false || v === "" || v === 0 || v === 0n) return false;
  if (v instanceof PyFloat) return v.value !== 0;
  if (Array.isArray(v)) return v.length > 0;
  if (isDict(v)) return Object.keys(v).length > 0;
  return true;
}

export function typeName(v) {
  if (typeof v === "string") return "str";
  if (typeof v === "boolean") return "bool";
  if (v === null || v === undefined) return "NoneType";
  if (Array.isArray(v)) return "list";
  if (isPyFloat(v)) return "float";
  if (isPyInt(v)) return "int";
  return "dict";
}

/** Python ==, where 1 == 1.0 == True. Used for `value in enum`. */
export function pyEq(a, b) {
  const numeric = (v) => typeof v === "boolean" || typeof v === "number" || typeof v === "bigint" || v instanceof PyFloat;
  if (numeric(a) && numeric(b)) {
    const x = typeof a === "boolean" ? Number(a) : num(a);
    const y = typeof b === "boolean" ? Number(b) : num(b);
    if (typeof a === "bigint" && typeof b === "bigint") return a === b;
    return x === y;
  }
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => pyEq(x, b[i]));
  if (isDict(a) && isDict(b)) {
    const ka = Object.keys(a);
    return ka.length === Object.keys(b).length && ka.every((k) => Object.hasOwn(b, k) && pyEq(a[k], b[k]));
  }
  if ((a === null || a === undefined) && (b === null || b === undefined)) return true;
  return a === b;
}

// --- strings --------------------------------------------------------------------

// str.isspace(), which is not JavaScript's \s: Python adds \x1c-\x1f and \x85,
// JavaScript adds U+FEFF.
const WS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const STRIP = new RegExp(`^[${WS}]+|[${WS}]+$`, "gu");

export const strip = (s) => s.replace(STRIP, "");
/** len() counts code points; JavaScript's .length counts UTF-16 units. */
export const len = (s) => [...s].length;
export const slice = (s, a, b) => [...s].slice(a, b).join("");
export const ljust = (s, w) => s + " ".repeat(Math.max(0, w - len(s)));
export const rjust = (s, w) => " ".repeat(Math.max(0, w - len(s))) + s;
/** Python's default string ordering: by code point, not by UTF-16 unit. */
export function cmpCodePoints(a, b) {
  const x = [...a], y = [...b];
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d) return d;
  }
  return x.length - y.length;
}

// --- regex: Python's `re` semantics on a JavaScript engine ----------------------

// Python's \w, \d, \s and \b are Unicode-aware on str patterns; JavaScript's are
// ASCII-only even with the u flag, and `.` excludes only \n in Python. These are
// the only differences the lesson's patterns touch, so only these are translated.
const W = "\\p{L}\\p{N}_";
const WORD = `[${W}]`;
const OUTSIDE = { w: WORD, d: "\\p{Nd}", s: `[${WS}]`, b: `(?:(?<=${WORD})(?!${WORD})|(?<!${WORD})(?=${WORD}))` };
const INSIDE = { w: W, d: "\\p{Nd}", s: WS };

/** Compile a Python regex string. `dotAll` is re.S; `g` for findall/sub. */
export function pyRegex(src, { dotAll = false, g = false } = {}) {
  let out = "";
  let inClass = false;
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (ch === "\\") {
      const nx = src[++i];
      out += (inClass ? INSIDE : OUTSIDE)[nx] ?? "\\" + nx;
    } else if (ch === "[" && !inClass) {
      inClass = true;
      out += ch;
    } else if (ch === "]" && inClass && src[i - 1] !== "[" && src.slice(i - 2, i) !== "[^") {
      inClass = false;
      out += ch;
    } else {
      out += ch === "." && !inClass && !dotAll ? "[^\\n]" : ch;
    }
  }
  return new RegExp(out, "u" + (dotAll ? "s" : "") + (g ? "g" : ""));
}

/** re.findall for a pattern with exactly one group. */
export const findall = (re, text) => [...text.matchAll(re)].map((m) => m[1]);

// --- floats ---------------------------------------------------------------------

function decompose(x) {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, x);
  const hi = view.getUint32(0), lo = view.getUint32(4);
  const bits = (hi >>> 20) & 0x7ff;
  let mant = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
  let exp = -1074;
  if (bits) {
    mant |= 1n << 52n;
    exp = bits - 1075;
  }
  return { neg: hi >>> 31 === 1, mant, exp };
}

/** f"{x:.{d}f}": exact value, round half to even. toFixed() rounds ties away. */
export function formatFixed(x, d) {
  x = num(x);
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  const { neg, mant, exp } = decompose(x);
  // value = numer / 10^k, exactly
  let numer, k;
  if (exp >= 0) {
    numer = mant << BigInt(exp);
    k = 0;
  } else {
    k = -exp;
    numer = mant * 5n ** BigInt(k);
  }
  let q;
  if (k <= d) {
    q = numer * 10n ** BigInt(d - k);
  } else {
    const den = 10n ** BigInt(k - d);
    q = numer / den;
    const r2 = (numer % den) * 2n;
    if (r2 > den || (r2 === den && q % 2n === 1n)) q += 1n;
  }
  const s = q.toString().padStart(d + 1, "0");
  return (neg ? "-" : "") + (d ? s.slice(0, -d) + "." + s.slice(-d) : s);
}

/** round(x, d) for a float: CPython rounds the exact value, half to even. */
export const pyRound = (x, d) => Number(formatFixed(x, d));

/** repr(float): shortest round-trip digits, as JavaScript, but Python's layout. */
function floatRepr(x) {
  if (Number.isNaN(x)) return "nan";
  if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
  if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
  const [mant, e10] = x.toExponential().split("e");
  const digits = mant.replace("-", "").replace(".", "");
  const e = Number(e10);
  const sign = x < 0 ? "-" : "";
  if (e >= -4 && e < 16) {
    if (e >= 0) {
      const whole = digits.slice(0, e + 1).padEnd(e + 1, "0");
      return `${sign}${whole}.${digits.slice(e + 1) || "0"}`;
    }
    return `${sign}0.${"0".repeat(-e - 1)}${digits}`;
  }
  const m = digits[0] + (digits.length > 1 ? "." + digits.slice(1) : "");
  return `${sign}${m}e${e < 0 ? "-" : "+"}${String(Math.abs(e)).padStart(2, "0")}`;
}

// --- repr() and str() -----------------------------------------------------------

const NON_PRINTABLE = /[\p{C}\p{Z}]/u;

function reprStr(s) {
  const q = s.includes("'") && !s.includes('"') ? '"' : "'";
  let out = q;
  for (const ch of s) {
    const cp = ch.codePointAt(0);
    if (ch === q || ch === "\\") out += "\\" + ch;
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (cp < 0x20 || cp === 0x7f) out += "\\x" + cp.toString(16).padStart(2, "0");
    else if (cp < 0x7f || !NON_PRINTABLE.test(ch)) out += ch;
    else if (cp <= 0xff) out += "\\x" + cp.toString(16).padStart(2, "0");
    else if (cp <= 0xffff) out += "\\u" + cp.toString(16).padStart(4, "0");
    else out += "\\U" + cp.toString(16).padStart(8, "0");
  }
  return out + q;
}

export function repr(v) {
  if (typeof v === "string") return reprStr(v);
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  if (typeof v === "bigint") return v.toString();
  if (v instanceof PyFloat) return floatRepr(v.value);
  if (typeof v === "number") return Number.isInteger(v) ? BigInt(v).toString() : floatRepr(v);
  if (Array.isArray(v)) return "[" + v.map(repr).join(", ") + "]";
  return "{" + Object.entries(v).map(([k, x]) => `${repr(k)}: ${repr(x)}`).join(", ") + "}";
}

/** str(): a string as itself, anything else as repr(). */
export const str = (v) => (typeof v === "string" ? v : repr(v));

// --- json.dumps -----------------------------------------------------------------

function dumpStr(s, ensureAscii) {
  // For well-formed strings JSON.stringify escapes exactly what Python does
  // (\" \\ \b \f \n \r \t, other controls as \u00xx) and leaves the rest;
  // ensure_ascii also escapes DEL and everything past it.
  const body = JSON.stringify(s);
  if (!ensureAscii) return body;
  return body.replace(/[^\x00-\x7e]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
}

/** json.dumps(v, sort_keys=?, ensure_ascii=?) with Python's default separators. */
export function dumps(v, { sortKeys = false, ensureAscii = true } = {}) {
  const go = (x) => {
    if (typeof x === "string") return dumpStr(x, ensureAscii);
    if (x === null || x === undefined) return "null";
    if (typeof x === "boolean") return x ? "true" : "false";
    if (typeof x === "bigint") return x.toString();
    if (x instanceof PyFloat || (typeof x === "number" && !Number.isInteger(x))) {
      const f = num(x);
      if (Number.isNaN(f)) return "NaN";
      if (!Number.isFinite(f)) return f > 0 ? "Infinity" : "-Infinity";
      return floatRepr(f);
    }
    if (typeof x === "number") return BigInt(x).toString();
    if (Array.isArray(x)) return x.length ? "[" + x.map(go).join(", ") + "]" : "[]";
    let keys = Object.keys(x);
    if (sortKeys) keys = keys.sort(cmpCodePoints);
    if (!keys.length) return "{}";
    return "{" + keys.map((k) => dumpStr(k, ensureAscii) + ": " + go(x[k])).join(", ") + "}";
  };
  return go(v);
}

// --- json.loads -----------------------------------------------------------------

class JSONDecodeError extends Error {}

/** json.loads: NaN/Infinity accepted, control characters in strings refused,
 *  and floats kept distinct from ints. */
export function loads(text) {
  let i = 0;
  const fail = (msg) => {
    throw new JSONDecodeError(`${msg}: char ${i}`);
  };
  const ws = () => {
    while (i < text.length && " \t\n\r".includes(text[i])) i++;
  };
  const NUMBER = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/y;

  const value = () => {
    const c = text[i];
    if (c === '"') return string();
    if (c === "{") return object();
    if (c === "[") return array();
    for (const [word, v] of [["null", null], ["true", true], ["false", false],
      ["NaN", new PyFloat(NaN)], ["Infinity", new PyFloat(Infinity)], ["-Infinity", new PyFloat(-Infinity)]]) {
      if (text.startsWith(word, i)) {
        i += word.length;
        return v;
      }
    }
    NUMBER.lastIndex = i;
    const m = NUMBER.exec(text);
    if (!m) fail("Expecting value");
    i += m[0].length;
    if (m[1] || m[2]) return new PyFloat(Number(m[0]));
    const n = Number(m[0]);
    return Number.isSafeInteger(n) ? n : BigInt(m[0]);
  };

  const string = () => {
    i++;
    let out = "";
    for (;;) {
      if (i >= text.length) fail("Unterminated string starting at");
      const c = text[i++];
      if (c === '"') return out;
      if (c < " ") fail("Invalid control character at");
      if (c !== "\\") {
        out += c;
        continue;
      }
      const e = text[i++];
      const simple = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };
      if (e in simple) out += simple[e];
      else if (e === "u" && /^[0-9a-fA-F]{4}$/.test(text.slice(i, i + 4))) {
        out += String.fromCharCode(parseInt(text.slice(i, i + 4), 16));
        i += 4;
      } else fail("Invalid \\escape");
    }
  };

  const array = () => {
    i++;
    const out = [];
    ws();
    if (text[i] === "]") {
      i++;
      return out;
    }
    for (;;) {
      ws();
      out.push(value());
      ws();
      if (text[i] === ",") i++;
      else if (text[i] === "]") {
        i++;
        return out;
      } else fail("Expecting ',' delimiter");
    }
  };

  const object = () => {
    i++;
    const out = {};
    ws();
    if (text[i] === "}") {
      i++;
      return out;
    }
    for (;;) {
      ws();
      if (text[i] !== '"') fail("Expecting property name enclosed in double quotes");
      const key = string();
      ws();
      if (text[i++] !== ":") fail("Expecting ':' delimiter");
      ws();
      out[key] = value();
      ws();
      if (text[i] === ",") i++;
      else if (text[i] === "}") {
        i++;
        return out;
      } else fail("Expecting ',' delimiter");
    }
  };

  ws();
  const v = value();
  ws();
  if (i !== text.length) fail("Extra data");
  return v;
}
