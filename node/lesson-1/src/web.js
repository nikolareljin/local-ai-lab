// Tiny Express web UI: drag-and-drop documents + ask questions.
//
// Reuses the same engine as the CLI. Endpoints mirror localrag/web.py:
//   GET  /             -> the single-page UI
//   GET  /api/status   -> current provider/retriever defaults + indexed files
//   POST /api/upload   -> save dropped files into the docs folder, reindex
//   POST /api/ask      -> answer a question grounded in the documents

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import express from "express";
import multer from "multer";

import { loadConfig } from "./config.js";
import { answerQuestion, getRetriever, refreshIndex } from "./engine.js";
import { SUPPORTED_EXTS, discoverFiles } from "./extract.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function listFiles(config) {
  return discoverFiles(config.docsDir).map((p) => path.basename(p));
}

// werkzeug.secure_filename equivalent: strip directory parts and unsafe chars,
// then trim leading AND trailing dots/underscores/dashes (matching the .NET port;
// Windows normalizes trailing dots/spaces, which can cause surprise overwrites).
function secureFilename(name) {
  let base = path.basename(name).replace(/[^A-Za-z0-9_.-]/g, "_");
  base = base.replace(/^[._-]+|[._-]+$/g, "");
  return base || "file";
}

export function createApp(baseConfig) {
  baseConfig = baseConfig || loadConfig();
  fs.mkdirSync(baseConfig.docsDir, { recursive: true });

  const app = express();
  app.use(express.json({ limit: "64mb" }));
  // memoryStorage buffers each file in RAM, so cap both the per-file size and the
  // number of files per request — otherwise a single multi-file upload could
  // exhaust memory. This keeps the worst-case bounded, matching the total-request
  // caps the Python (MAX_CONTENT_LENGTH) and .NET (MaxRequestBodySize) ports use.
  const upload = multer({
    storage: multer.memoryStorage(),
    limits: {
      fileSize: 64 * 1024 * 1024, // 64 MB per-file cap
      files: 20, // bound how many files one request can buffer at once
    },
  });
  // Translate multer limit violations into clear 413s instead of generic 500s.
  function uploadFiles(req, res, next) {
    upload.array("files")(req, res, (err) => {
      if (!err) return next();
      if (err instanceof multer.MulterError) {
        const reason =
          err.code === "LIMIT_FILE_SIZE"
            ? "A file exceeds the 64 MB limit."
            : err.code === "LIMIT_FILE_COUNT"
              ? "Too many files in one upload (max 20)."
              : err.message;
        return res.status(413).json({ error: reason });
      }
      return next(err);
    });
  }

  // Per-request config with optional provider/retriever overrides.
  function requestConfig(body) {
    const data = body || {};
    const overrides = {};
    if (data.provider) overrides.provider = String(data.provider).toLowerCase();
    if (data.retriever) overrides.retriever = String(data.retriever).toLowerCase();
    return Object.keys(overrides).length ? { ...baseConfig, ...overrides } : baseConfig;
  }

  const templatePath = path.join(__dirname, "templates", "index.html");

  app.get("/", (req, res) => {
    res.type("html").send(fs.readFileSync(templatePath, "utf-8"));
  });

  app.get("/api/status", (req, res) => {
    res.json({
      provider: baseConfig.provider,
      retriever: baseConfig.retriever,
      docs_dir: baseConfig.docsDir,
      files: listFiles(baseConfig),
      supported: [...SUPPORTED_EXTS].sort(),
      links: {
        linkedin: baseConfig.linkedinUrl,
        github: baseConfig.githubUrl,
        tutorial: baseConfig.tutorialUrl,
        troubleshooting: baseConfig.docsBaseUrl + "troubleshooting.html",
      },
    });
  });

  app.post("/api/upload", uploadFiles, async (req, res) => {
    const saved = [];
    const skipped = [];
    for (const f of req.files || []) {
      if (!f.originalname) continue;
      const name = secureFilename(f.originalname);
      if (!SUPPORTED_EXTS.has(path.extname(name).toLowerCase())) {
        skipped.push(f.originalname);
        continue;
      }
      // Async write so a large upload doesn't block the event loop (and other
      // concurrent requests) while bytes are flushed to disk.
      await fs.promises.writeFile(path.join(baseConfig.docsDir, name), f.buffer);
      saved.push(name);
    }

    const { chunks, fileCount } = await refreshIndex(baseConfig);
    res.json({
      saved,
      skipped,
      files: listFiles(baseConfig),
      indexed_files: fileCount,
      chunks: chunks.length,
    });
  });

  app.post("/api/ask", async (req, res) => {
    const data = req.body || {};
    const question = (data.question || "").trim();
    if (!question) {
      return res.status(400).json({ error: "Please enter a question." });
    }
    try {
      const result = await answerQuestion(requestConfig(data), question);
      res.json(result);
    } catch (exc) {
      // Surface provider/network errors to the UI.
      res.status(500).json({ error: String(exc.message || exc) });
    }
  });

  // The raw numbers behind the index — "How the system sees your data".
  app.get("/api/peek", async (req, res) => {
    const config = requestConfig(req.query);
    const question = (req.query.q || "").toString().trim();
    try {
      const retriever = await getRetriever(config);
      if (typeof retriever.peek !== "function") {
        return res.status(400).json({
          error: `The '${retriever.name}' retriever has no peek view yet — switch to BM25.`,
        });
      }
      res.json(retriever.peek(question || null, config.topK));
    } catch (exc) {
      res.status(500).json({ error: String(exc.message || exc) });
    }
  });

  return app;
}

export function run(host = "127.0.0.1", port = 5000, config = null) {
  const app = createApp(config);
  app.listen(port, host, () => {
    console.log(`[localrag] Web UI on http://${host}:${port}  (Ctrl-C to stop)`);
  });
}
