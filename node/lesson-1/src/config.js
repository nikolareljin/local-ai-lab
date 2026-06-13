// Configuration loaded from environment / repo-root .env. No hard-coded paths.
// Mirrors localrag/config.py field-for-field. The only deliberate difference:
// the cache dir is <repoRoot>/.localrag/node so it never clobbers the Python index.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Project root is three levels up: node/lesson-1/src -> repo root.
function repoRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

// Tiny hand-rolled .env parser (dependency-light). Only sets vars that are not
// already present in the environment, matching python-dotenv's default behavior.
function loadDotEnv(root) {
  const envPath = path.join(root, ".env");
  let text;
  try {
    text = fs.readFileSync(envPath, "utf-8");
  } catch {
    return;
  }
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    if (!key || key in process.env) continue;
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}

function env(name, fallback) {
  const v = process.env[name];
  return v === undefined || v === "" ? fallback : v;
}

function stripTrailingSlash(s) {
  return s.replace(/\/+$/, "");
}

function ensureTrailingSlash(s) {
  return s.replace(/\/+$/, "") + "/";
}

export function loadConfig() {
  const root = repoRoot();
  loadDotEnv(root);

  let docsDir = env("RAG_DOCS_DIR", "documents");
  if (!path.isAbsolute(docsDir)) {
    docsDir = path.join(root, docsDir);
  }

  return {
    provider: env("RAG_PROVIDER", "claude").toLowerCase(),
    retriever: env("RAG_RETRIEVER", "bm25").toLowerCase(),
    embedProvider: env("RAG_EMBED_PROVIDER", "ollama").toLowerCase(),
    docsDir,
    // NOTE: .localrag/node (not .localrag/) so the Node index never collides
    // with the Python reference index.
    cacheDir: path.join(root, ".localrag", "node"),
    // Guard against a non-numeric or non-positive RAG_TOP_K (would become NaN and
    // break slice/ranking); fall back to the default of 5.
    topK: (() => {
      const v = parseInt(env("RAG_TOP_K", "5"), 10);
      return Number.isFinite(v) && v > 0 ? v : 5;
    })(),

    // Social / course links surfaced in the web UI.
    linkedinUrl: env("LINKEDIN_URL", "https://www.linkedin.com/in/nikolareljin"),
    githubUrl: env("GITHUB_URL", "https://github.com/nikolareljin/local-ai-lab"),
    tutorialUrl: env("TUTORIAL_URL", "https://nikolareljin.github.io/local-ai-lab/"),
    // Base URL of the docs site (trailing slash). Override (e.g.
    // http://localhost:8000/) to point Troubleshooting links at a LOCAL copy.
    docsBaseUrl: ensureTrailingSlash(
      env("DOCS_BASE_URL", "https://nikolareljin.github.io/local-ai-lab/")
    ),

    // Provider settings.
    claudeBin: env("CLAUDE_BIN", "claude"),
    ollamaUrl: stripTrailingSlash(env("OLLAMA_URL", "http://localhost:11434")),
    ollamaModel: env("OLLAMA_MODEL", "llama3.1:8b"),
    ollamaEmbedModel: env("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
    geminiApiKey: env("GEMINI_API_KEY", ""),
    geminiModel: env("GEMINI_MODEL", "gemini-2.5-flash"),
    geminiEmbedModel: env("GEMINI_EMBED_MODEL", "text-embedding-004"),
    openaiApiKey: env("OPENAI_API_KEY", ""),
    openaiBaseUrl: stripTrailingSlash(env("OPENAI_BASE_URL", "https://api.openai.com/v1")),
    openaiModel: env("OPENAI_MODEL", "gpt-4o-mini"),
    openaiEmbedModel: env("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
  };
}
