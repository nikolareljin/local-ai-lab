// Lesson 10 - the System One API by hand, in Node.js (the twin of python/systemone.py).
//
// The official SDK (sdk_example.mjs) is the comfortable way to call Jev. This file is
// the uncomfortable one, on purpose: it shows that the whole API is one HTTP POST, and
// it holds the rule about where a request may go.
//
//     POST <base>/v1/systemone
//     Authorization: Bearer <TYPESAFE_API_KEY>
//     {"model": "jev-latest", "state": "...", "questions": {"emergency": {...}}}
//
// Standard library only: `fetch` is built into Node 18 and later.

import { isIPv6 } from "node:net";

export const TYPESAFE_URL = "https://api.typesafe.ai";
export const SYSTEM_ONE_PATH = "/v1/systemone";

/**
 * Is this an http(s) URL whose host is this machine (localhost, 127.x.x.x or ::1)?
 *
 * Parsed by hand, strictly, and the same way in Python and C#: the three languages'
 * URL libraries disagree on odd inputs ("127.1", a backslash, an unclosed bracket),
 * and a check that guards where an API key may be sent must not depend on which
 * parser happens to read the string.
 */
export function isLoopback(url) {
  if (url.includes("\\")) return false; // parsers disagree on what a backslash means
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

/** Refuse anything but TypeSafe's API or this machine. Throws with the reason. */
export function checkDestination(baseUrl) {
  if (!(baseUrl.replace(/\/+$/, "") === TYPESAFE_URL || isLoopback(baseUrl))) {
    throw new Error(`refusing ${baseUrl}: only ${TYPESAFE_URL} or a loopback address`);
  }
}

/**
 * POST one System One request; resolve to { response, seconds }.
 *
 * `body` is { model, state, questions }. The key goes in a Bearer header, and only ever
 * to TypeSafe or to this machine: checkDestination() runs first, so a typo in
 * TYPESAFE_BASE_URL cannot hand the key (or the calls) to a stranger.
 */
export async function post(baseUrl, body, apiKey = "", timeoutMs = 120_000) {
  checkDestination(baseUrl);
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers.Authorization = `Bearer ${apiKey}`;
  const started = performance.now();
  let reply;
  try {
    reply = await fetch(baseUrl.replace(/\/+$/, "") + SYSTEM_ONE_PATH, {
      method: "POST", headers, body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    throw new Error(`cannot reach ${baseUrl}: ${err.cause?.message ?? err.message}`);
  }
  if (!reply.ok) {
    // 401 bad key, 422 a malformed question, 429 rate limit: show what the server said.
    throw new Error(`HTTP ${reply.status} from ${baseUrl}: ${(await reply.text()).slice(0, 300)}`);
  }
  return { response: await reply.json(), seconds: (performance.now() - started) / 1000 };
}
