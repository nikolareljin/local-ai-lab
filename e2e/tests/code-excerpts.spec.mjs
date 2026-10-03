// Every code step on every lesson page shows the code its lesson.json names, in the
// language the reader picked, and nothing else.
//
// The pages are built from line ranges. When a range goes stale the page still renders,
// with the wrong lines (Lesson 6 once opened a step on `"end": last + 1,`). Here the
// browser's view of each step is compared with the excerpt computed from the source.
import { expect, test } from "@playwright/test";
import { expectations, offline } from "./site.mjs";

const steps = expectations();
const pages = [...new Set(steps.map((s) => s.page))];
const LANGS = ["python", "node", "csharp"];

/** All <pre> blocks of the page: their non-blank lines, slide number and language wrapper. */
async function blocks(page) {
  return page.evaluate(() => {
    const slides = Array.from(document.querySelectorAll("section.slide"));
    return Array.from(document.querySelectorAll("section.slide pre")).map((pre, index) => {
      const wrapper = pre.closest(".lang");
      // textContent, not innerText: innerText is empty for a step that is not open.
      const lines = pre.textContent.split("\n").map((l) => l.trim()).filter(Boolean);
      return {
        index,
        slide: slides.indexOf(pre.closest("section.slide")) + 1,
        lang: wrapper ? ["python", "node", "csharp"].find((l) => wrapper.classList.contains(`lang-${l}`)) : null,
        shownForLanguage: !wrapper || getComputedStyle(wrapper).display !== "none",
        first: lines[0] ?? "", last: lines.at(-1) ?? "", count: lines.length,
      };
    });
  });
}

// A step outside a language group has no wrapper and is shown in every language.
const same = (block, step) => block.first === step.first && block.last === step.last
  && block.count === step.count && (block.lang === step.lang || block.lang === null);

for (const name of pages) {
  const mine = steps.filter((s) => s.page === name);
  const langs = LANGS.filter((l) => mine.some((s) => s.lang === l));

  test.describe(name, () => {
    test.beforeEach(async ({ page }) => { await offline(page); });

    test("every code step is on the page, complete", async ({ page }) => {
      await page.goto(name);
      const found = await blocks(page);
      for (const step of mine) {
        const hit = found.filter((b) => same(b, step));
        expect(hit.length, `${step.file} ${step.lines} (${step.symbol}), ${step.lang}: expected a block of ${step.count} lines from "${step.first}" to "${step.last}"`).toBeGreaterThan(0);
      }
      // A stale range shows up as a block that starts inside another statement.
      for (const block of found.filter((b) => b.lang)) {
        expect(block.first, `step ${block.slide}: a ${block.lang} block starts with a closing bracket`).not.toMatch(/^[)\]}]/);
      }
    });

    for (const lang of langs) {
      test(`with ${lang} selected, each step shows ${lang} and only ${lang}`, async ({ page }) => {
        await page.goto(name);
        // A lesson in one language has no selector; the page is already in that language.
        const selector = page.locator(`[data-setlang="${lang}"]`).first();
        if (await selector.count()) await selector.click();
        await expect(page.locator("html")).toHaveAttribute("data-lang", lang);
        const found = await blocks(page);
        for (const block of found.filter((b) => b.lang)) {
          expect(block.shownForLanguage, `step ${block.slide}: a ${block.lang} block while ${lang} is selected`).toBe(block.lang === lang);
        }
        // Open each step of this language and look at it the way a reader does.
        for (const step of mine.filter((s) => s.lang === lang)) {
          const block = found.find((b) => same(b, step));
          expect(block, `${step.file} (${step.symbol}) is missing`).toBeTruthy();
          await page.goto(`${name}#step-${block.slide}`);
          await page.reload();
          await expect(page.locator(".counter").first()).toContainText(`Step ${block.slide} of`);
          const pre = page.locator("section.slide pre").nth(block.index);
          await expect(pre).toBeVisible();
          await expect(pre).toContainText(step.first);
          // No other language's code is visible on the open step.
          const visible = await page.locator("section.slide.active .lang:visible").evaluateAll(
            (nodes) => nodes.map((n) => n.className));
          for (const cls of visible) expect(cls).toContain(`lang-${lang}`);
        }
      });
    }
  });
}
