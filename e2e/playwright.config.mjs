// Browser tests for the published pages. They run against docs/ exactly as GitHub Pages
// serves it: a static file server on loopback, no build step in between.
import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.E2E_PORT ?? 4173);
// E2E_DOCS points the suite at another copy of the site (used to prove it fails on a
// stale one). Default: the docs/ folder of this checkout.
const DOCS = process.env.E2E_DOCS ?? "../docs";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: `http://127.0.0.1:${PORT}/` },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `python3 -m http.server ${PORT} --bind 127.0.0.1 --directory ${DOCS}`,
    url: `http://127.0.0.1:${PORT}/index.html`,
    reuseExistingServer: false,
  },
});
