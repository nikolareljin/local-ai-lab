// What the tests need to know about the site, read from the repository itself.
import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** Every code step of every lesson, as tools/lesson_lines.py computes it from the sources. */
export function expectations() {
  const out = execFileSync("python3", ["tools/lesson_lines.py", "--expect"], { cwd: ROOT, encoding: "utf8" });
  return JSON.parse(out);
}

/** The lesson pages in docs/, generated and hand-written. */
export function lessonPages() {
  return readdirSync(resolve(ROOT, "docs")).filter((f) => /^lesson-\d+-.*\.html$/.test(f)).sort();
}

/** Requests to other hosts (analytics, badges) are cut off: the tests are about this site. */
export async function offline(page) {
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => route.abort());
}
