// Lesson 10 - the official TypeSafe SDK, against TypeSafe's Jev or the local adapter.
// Node.js version of python/sdk_example.py.
//
// The same code, two destinations. Only the environment changes:
//
//   TypeSafe (internet, real Jev):   TYPESAFE_API_KEY=<your key>
//   local adapter (simulated):       TYPESAFE_BASE_URL=http://127.0.0.1:8765 TYPESAFE_API_KEY=local
//                                    (start it first: ./run -l 10 serve)
//
//     cd lessons/10-jev-system-one/node && npm ci      # once: the pinned SDK
//     node sdk_example.mjs "I was charged twice, please refund one"

import { formatFixed, roundEven } from "./pycompat.mjs";

let sdk;
try {
  sdk = await import("@typesafe-ai/sdk");
} catch {
  console.error("Run: cd lessons/10-jev-system-one/node && npm ci");
  process.exit(1);
}
const { TypeSafeClient, choice, noul, score } = sdk;

const text = process.argv.slice(2).join(" ") || "I was charged twice for my Pro plan. Please refund one.";
const url = process.env.TYPESAFE_BASE_URL || "https://api.typesafe.ai";
if (url.includes("typesafe.ai")) {
  console.log("Sending this text to TypeSafe (it leaves this machine). Use fake data only.");
}

// --- the whole integration -------------------------------------------------
const client = new TypeSafeClient(); // reads TYPESAFE_API_KEY and TYPESAFE_BASE_URL
const result = await client.systemOne({
  state: text,
  questions: {
    queue: choice("Which team queue should handle this support ticket?", {
      billing: "Charges, invoices, refunds",
      technical: "Bugs, outages, errors",
      account: "Login, users, account changes",
      sales: "Pricing, upgrades, quotes",
      trust_safety: "Security, takeover, data exposure, abuse",
    }),
    urgency: score("How urgent is it for the business?", ["none", "low", "medium", "high", "critical"]),
    refund_request: noul("Does the customer ask for money back?"),
  },
});
const { queue, urgency, refund_request: refund } = result.answers;
// -----------------------------------------------------------------------------

const f2 = (x) => formatFixed(x, 2);
console.log(`model    ${result.model}`);
console.log(`queue    ${queue.choice}  (confidence ${f2(queue.confidence)})`);
console.log("         " + Object.entries(queue.probabilities).map(([k, v]) => `${k} ${f2(v)}`).join("  "));
console.log(`urgency  ${urgency.legend[roundEven(urgency.score)]}  (score ${f2(urgency.score)} of 0-4)`);
console.log(`refund   P(yes) = ${f2(refund.noul)}`);
