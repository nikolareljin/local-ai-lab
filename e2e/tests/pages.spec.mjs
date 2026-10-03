// Every lesson page loads cleanly and its slider reaches every step.
import { expect, test } from "@playwright/test";
import { lessonPages, offline } from "./site.mjs";

for (const name of lessonPages()) {
  test(`${name}: loads without errors and every step opens`, async ({ page }) => {
    const errors = [];
    page.on("console", (m) => { if (m.type() === "error" && !/ERR_FAILED|Failed to load resource/.test(m.text())) errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("response", (r) => { if (r.url().startsWith("http://127.0.0.1") && r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });
    await offline(page);
    await page.goto(name);

    const total = await page.locator("section.slide").count();
    expect(total).toBeGreaterThan(3);
    await expect(page.locator("section.slide.active")).toHaveCount(1);
    const next = page.locator("[data-next]").first();
    for (let step = 2; step <= total; step++) {
      await next.click();
      await expect(page).toHaveURL(new RegExp(`#step-${step}$`));
      await expect(page.locator("section.slide.active")).toHaveCount(1);
      // A step with nothing in it is a rendering failure, not a short step.
      expect((await page.locator("section.slide.active").innerText()).trim().length).toBeGreaterThan(20);
    }
    await expect(next).toBeDisabled();
    // No reference to a file that was not found, in any step.
    await expect(page.locator("body")).not.toContainText(/\[(missing file|invalid lines spec|blocked path)/);
    expect(errors).toEqual([]);
  });
}
