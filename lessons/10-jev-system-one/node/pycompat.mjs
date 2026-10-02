// Lesson 10 - the few Python behaviours the demo's output depends on, in Node.
//
// The demo has to print exactly what python/jev.py prints, and refuse exactly the
// recordings it refuses. That needs Python's float formatting (round half to even
// on the exact binary value; toFixed() rounds ties away), Python's repr() for the
// llm-json error lines, json.loads (NaN accepted, 3 and 3.0 kept apart), and the
// canonical json.dumps the cassette digest is computed over.

// --- values -------------------------------------------------------------------

/** A JSON number written with a fraction or exponent: a Python float, not an int. */
export class PyFloat {
  constructor(value) {
    this.value = value;
  }
}

/** A parsed number (int, BigInt or PyFloat) as a JS number, for arithmetic. */
export function num(v) {
  if (v instanceof PyFloat) return v.value;
  if (typeof v === "bigint") return Number(v);
  return v;
}

export const isDict = (v) =>
  v !== null && typeof v === "object" && !Array.isArray(v) && !(v instanceof PyFloat);

// --- strings --------------------------------------------------------------------

// str.isspace(), which is not JavaScript's \s: Python adds \x1c-\x1f and \x85,
// JavaScript adds U+FEFF.
const WS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const STRIP = new RegExp(`^[${WS}]+|[${WS}]+$`, "gu");

export const strip = (s) => s.replace(STRIP, "");
/** len() counts code points; JavaScript's .length counts UTF-16 units. */
export const len = (s) => [...s].length;
export const ljust = (s, w) => s + " ".repeat(Math.max(0, w - len(s)));
export const rjust = (s, w) => " ".repeat(Math.max(0, w - len(s))) + s;

function cmpCodePoints(a, b) {
  const x = [...a], y = [...b];
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d) return d;
  }
  return x.length - y.length;
}

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

/** f"{x:.{d}f}": exact value, round half to even. */
export function formatFixed(x, d) {
  x = num(typeof x === "boolean" ? Number(x) : x);
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

/** round(x) to an int: half to even. */
export function roundEven(x) {
  const f = Math.floor(x), diff = x - f;
  if (diff > 0.5) return f + 1;
  if (diff < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

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

/** sum() as CPython 3.12+ does it: ints added exactly until the first float, then
 *  floats with Neumaier compensation (ints after that added plainly). Values are
 *  parsed with floats: true, so a PyFloat is a float and a plain number an int. */
export function pySum(values) {
  let i = 0, ints = 0;
  for (; i < values.length && !(values[i] instanceof PyFloat); i++) ints += Number(values[i]);
  if (i === values.length) return ints;
  let f = ints + values[i].value, c = 0.0;
  for (i++; i < values.length; i++) {
    const v = values[i];
    if (!(v instanceof PyFloat)) {
      f += Number(v);
      continue;
    }
    const x = v.value, t = f + x;
    c += Math.abs(f) >= Math.abs(x) ? (f - t) + x : (x - t) + f;
    f = t;
  }
  return c && Number.isFinite(c) ? f + c : f;
}

/** sum() over values that are all floats. */
export const pySumFloats = (xs) => pySum(xs.map((x) => new PyFloat(x)));

// --- repr() ---------------------------------------------------------------------

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
  return "{" + Object.keys(v).map((k) => `${repr(k)}: ${repr(v[k])}`).join(", ") + "}";
}

// --- json -----------------------------------------------------------------------

/** json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":")) for
 *  strings, ints, bools, None, lists and dicts - what a digest is taken over. */
export function canonical(x) {
  if (typeof x === "string") return JSON.stringify(x);
  if (x === null || x === undefined) return "null";
  if (typeof x === "boolean") return x ? "true" : "false";
  if (typeof x === "bigint") return x.toString();
  if (x instanceof PyFloat || (typeof x === "number" && !Number.isInteger(x))) {
    throw new Error("canonical(): floats are not supported");
  }
  if (typeof x === "number") return BigInt(x).toString();
  if (Array.isArray(x)) return "[" + x.map(canonical).join(",") + "]";
  const keys = Object.keys(x).sort(cmpCodePoints);
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonical(x[k])).join(",") + "}";
}

export class JSONDecodeError extends Error {}

/** json.loads: NaN/Infinity accepted, control characters in strings refused.
 *  With floats: true a float stays a PyFloat (for repr); otherwise every
 *  number is a plain JS number. */
export function loads(text, { floats = false } = {}) {
  let i = 0;
  const fail = (msg) => {
    throw new JSONDecodeError(`${msg}: char ${i}`);
  };
  const ws = () => {
    while (i < text.length && " \t\n\r".includes(text[i])) i++;
  };
  const NUMBER = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][-+]?[0-9]+)?/y;
  const float = (x) => (floats ? new PyFloat(x) : x);

  const value = () => {
    const c = text[i];
    if (c === '"') return string();
    if (c === "{") return object();
    if (c === "[") return array();
    for (const [word, v] of [["null", null], ["true", true], ["false", false],
      ["NaN", NaN], ["Infinity", Infinity], ["-Infinity", -Infinity]]) {
      if (text.startsWith(word, i)) {
        i += word.length;
        return typeof v === "number" ? float(v) : v;
      }
    }
    NUMBER.lastIndex = i;
    const m = NUMBER.exec(text);
    if (!m) fail("Expecting value");
    i += m[0].length;
    if (m[1] || m[2]) return float(Number(m[0]));
    const n = Number(m[0]);
    return floats && !Number.isSafeInteger(n) ? BigInt(m[0]) : n;
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
      if (Object.hasOwn(simple, e)) out += simple[e];
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
      // defineProperty, so a "__proto__" key is data, as in a Python dict
      Object.defineProperty(out, key, { value: value(), enumerable: true, writable: true, configurable: true });
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
