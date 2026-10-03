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

import { isIPv6 } from "node:net";

import { formatFixed } from "./pycompat.mjs";

let sdk;
try {
  sdk = await import("@typesafe-ai/sdk");
} catch {
  console.error("Run: cd lessons/10-jev-system-one/node && npm ci");
  process.exit(1);
}
const { TypeSafeClient, choice, noul, score } = sdk;

const TYPESAFE_URL = "https://api.typesafe.ai";

/** An http(s) URL whose host is this machine - python/systemone.is_loopback. */
export function isLoopback(url) {
  url = url.replace(/[\t\r\n]/g, "").replace(/^[\x00-\x20]+/, "");
  const m = /^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^/?#]*)/.exec(url);
  if (!m || !["http", "https"].includes(m[1].toLowerCase())) return false;
  const netloc = m[2];
  if (netloc.includes("[") !== netloc.includes("]")) return false; // urlparse raises ValueError
  const hostinfo = netloc.slice(netloc.lastIndexOf("@") + 1);
  const open = hostinfo.indexOf("[");
  if (open >= 0) {
    const inside = hostinfo.slice(open + 1).split("]")[0];
    if (!isIPv6(inside)) return false; // urlparse accepts only an IPv6 address in brackets
    return new URL(`http://[${inside}]/`).hostname === "[::1]";
  }
  const host = hostinfo.split(":")[0].toLowerCase();
  if (host === "localhost") return true;
  // ipaddress.ip_address takes dotted quads only, no leading zeros.
  const octet = "(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])";
  return new RegExp(`^127\\.${octet}\\.${octet}\\.${octet}$`).test(host);
}

const text = process.argv.slice(2).join(" ") || "I was charged twice for my Pro plan. Please refund one.";
const url = process.env.TYPESAFE_BASE_URL ?? TYPESAFE_URL;
// TypeSafe or this machine, nothing else: a typo cannot hand the key to a stranger.
if (!(url.replace(/\/+$/, "") === TYPESAFE_URL || isLoopback(url))) {
  console.error(`refusing ${url}: only ${TYPESAFE_URL} or a loopback address`);
  process.exit(1);
}
if (!isLoopback(url)) {
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
// the most likely level, first one on a tie (keys are "0".."4", which JS keeps in order)
let level = null;
for (const [k, v] of Object.entries(urgency.probabilities)) if (level === null || v > urgency.probabilities[level]) level = k;
console.log(`urgency  ${urgency.legend[level]}  (score ${f2(urgency.score)} of 0-4)`);
console.log(`refund   P(yes) = ${f2(refund.noul)}`);
