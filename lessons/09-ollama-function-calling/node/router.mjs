// Lesson 9 - Arm A: the router you would write if the model could not pick tools.
//
// Mirrors python/router.py: the same rules, in the same order, compiled with
// Python's regex semantics (see pycompat.pyRegex). Every rule was written by
// someone who had already read the questions; read it as the baseline the model
// has to beat.

import { pyRegex } from "./pycompat.mjs";

const MATH = pyRegex(String.raw`\d\s*(%|[-+*/x])\s*(of\s+)?\d|how many|\bpercent\b`);
const TICKET = pyRegex(String.raw`\b(open|create|file|raise)\b.*\bticket\b`);
const LIST = pyRegex(String.raw`\bwhich documents\b|\blist (my )?(documents|files)\b`);
const SMALLTALK = pyRegex(String.raw`^(hi|hello|hey)\b|\btranslate\b`);
const NOT_ARITHMETIC = pyRegex(String.raw`\b(what|is|of)\b|[\d\s.%?+\-*/x]`, { g: true });

/** The tools a keyword router would call for `question`, in order. */
export function route(question) {
  const q = question.toLowerCase();
  if (TICKET.test(q)) return ["create_ticket"];
  if (LIST.test(q)) return ["list_documents"];
  if (SMALLTALK.test(q)) return [];
  const tools = [];
  // "What is 17.5% of 2340?" is arithmetic and nothing else: no search.
  if (q.replace(NOT_ARITHMETIC, "")) tools.push("search_docs");
  if (MATH.test(q)) tools.push("calculator");
  return tools;
}

const ORDER = pyRegex(String.raw`Call\s+create_ticket\s+with\s+severity\s+"(\w+)"\s+and\s+title\s+"([^"]+)"`, { dotAll: true });

/** A scripted 'model' that does whatever the last tool result tells it to.
 *  Real models mostly ignored ticket 9001's order, so this stand-in complies
 *  every time to show the intent guard catching it. Labelled as scripted
 *  everywhere it appears. */
export class ObedientStandIn {
  constructor() {
    this.turn = 0;
  }

  async chat(messages) {
    this.turn += 1;
    const last = messages[messages.length - 1];
    if (this.turn === 1) {
      const call = { function: { name: "search_docs", arguments: { query: messages[1].content } } };
      return { message: { role: "assistant", content: "", tool_calls: [call] }, seconds: 0.0 };
    }
    const m = ORDER.exec(last.content ?? "");
    if (m && this.turn === 2) {
      const call = { function: { name: "create_ticket", arguments: { title: m[2], severity: m[1] } } };
      return { message: { role: "assistant", content: "", tool_calls: [call] }, seconds: 0.0 };
    }
    return { message: { role: "assistant", content: "Your refund is on its way." }, seconds: 0.0 };
  }
}
