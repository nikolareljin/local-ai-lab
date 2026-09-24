// Lesson 9 - the calculator tool: a small grammar, never eval().
//
//   expr   := term (("+" | "-") term)*
//   term   := unary (("*" | "/" | "//" | "%") unary)*
//   unary  := ("+" | "-") unary | power
//   power  := atom (("**" | "^") unary)?
//   atom   := number | "(" expr ")"
//
// Line for line the grammar in python/tools.py, with the same error strings,
// so both runtimes give the same result and the same error for any input.

import { formatFixed, len, repr } from "./pycompat.mjs";

const NUMBER = String.raw`\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?`;
// ASCII only, as Python's re.ASCII: JavaScript's \s would also take a no-break space.
const SPACE = " \t\r\n\f\v";
const TOKEN = new RegExp(String.raw`[ \t\r\n\f\v]*(?:(${NUMBER})|(\*\*|//|[-+*/%^()]))`, "y");

class CalcError extends Error {}

/** Every intermediate must be a finite float, or floor() and pow() misbehave. */
function finite(value) {
  if (!Number.isFinite(value)) throw new CalcError("result too large");
  return value;
}

function tokens(text) {
  const out = [];
  let pos = 0;
  while (pos < text.length) {
    TOKEN.lastIndex = pos;
    const m = TOKEN.exec(text);
    if (!m) {
      let rest = text.slice(pos);
      while (rest && SPACE.includes(rest[0])) rest = rest.slice(1);
      if (!rest) break;
      // Python counts positions in code points, not UTF-16 units.
      throw new CalcError(`unexpected ${repr([...rest][0])} at position ${len(text) - len(rest)}`);
    }
    out.push(m[1] ?? m[2]);
    pos = TOKEN.lastIndex;
  }
  return out;
}

class Parser {
  constructor(toks) {
    this.t = toks;
    this.i = 0;
  }

  peek() {
    return this.i < this.t.length ? this.t[this.i] : null;
  }

  take() {
    const tok = this.peek();
    if (tok === null) throw new CalcError("expression ends too early");
    this.i += 1;
    return tok;
  }

  expr() {
    let value = this.term();
    while (["+", "-"].includes(this.peek())) {
      value = this.take() === "+" ? value + this.term() : value - this.term();
      finite(value);
    }
    return value;
  }

  term() {
    let value = this.unary();
    while (["*", "/", "//", "%"].includes(this.peek())) {
      const op = this.take(), right = this.unary();
      if (op !== "*" && right === 0) throw new CalcError("division by zero");
      if (op === "*") value = value * right;
      else if (op === "/") value = value / right;
      else if (op === "//") value = Math.floor(finite(value / right));
      else value = value - right * Math.floor(finite(value / right));
      finite(value);
    }
    return value;
  }

  unary() {
    if (["+", "-"].includes(this.peek())) return this.take() === "-" ? -this.unary() : this.unary();
    return this.power();
  }

  power() {
    const base = this.atom();
    if (["**", "^"].includes(this.peek())) {
      this.take();
      const exp = this.unary();
      if (Math.abs(exp) > 64) throw new CalcError("exponent too large");
      if (base < 0 && exp !== Math.trunc(exp)) throw new CalcError("result is not a real number");
      if (base === 0 && exp < 0) throw new CalcError("division by zero");
      return finite(Math.pow(base, exp)); // overflow is Infinity
    }
    return base;
  }

  atom() {
    const tok = this.take();
    if (tok === "(") {
      const value = this.expr();
      if (this.peek() !== ")") throw new CalcError("missing ')'");
      this.take();
      return value;
    }
    if (/^[0-9.]/.test(tok)) return finite(Number(tok)); // "1e400" is Infinity
    throw new CalcError(`unexpected ${repr(tok)}`);
  }
}

/** Evaluate plain arithmetic, or return `error: ...` for the model to read.
 *  Commas are refused rather than guessed at: "2,5" is a decimal in half the
 *  world and a thousands separator in the other half. */
export function calculate(expression) {
  if (len(expression) > 200) return "error: expression longer than 200 characters";
  let value;
  try {
    const parser = new Parser(tokens(expression));
    if (parser.peek() === null) throw new CalcError("expression is empty");
    value = parser.expr();
    if (parser.peek() !== null) throw new CalcError(`unexpected ${repr(parser.peek())}`);
  } catch (exc) {
    if (!(exc instanceof CalcError)) throw exc;
    return `error: ${exc.message}`;
  }
  if (!Number.isFinite(value) || Math.abs(value) >= 1e15) return "error: result too large";
  // formatFixed, not toFixed(6): on an exact tie toFixed rounds away from zero
  // and Python rounds half to even (1/128 is 0.007813 against 0.007812).
  const text = formatFixed(value, 6).replace(/0+$/, "").replace(/\.$/, "");
  return `${expression} = ${text === "-0" || text === "" ? "0" : text}`;
}
