// Build, cache, and load the document index.
//
// The index is just a JSON file of chunks (plus metadata) under the cache dir.
// Files are fingerprinted by (path, mtime, size) so re-indexing only happens
// when something changed. Mirrors localrag/store.py (BM25 only — no vectors).

import fs from "node:fs";
import path from "node:path";

import { chunkPages } from "./chunk.js";
import { discoverFiles, extractPages } from "./extract.js";

function fingerprint(files) {
  return files.map((p) => {
    const st = fs.statSync(p);
    return { path: p, mtime: Math.floor(st.mtimeMs / 1000), size: st.size };
  });
}

function indexPath(config) {
  return path.join(config.cacheDir, "index.json");
}

function fingerprintsEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function isStale(config) {
  // True if the cache is missing or the docs folder changed since last build.
  const ip = indexPath(config);
  if (!fs.existsSync(ip)) return true;
  let data;
  try {
    data = JSON.parse(fs.readFileSync(ip, "utf-8"));
  } catch {
    return true;
  }
  return !fingerprintsEqual(data.fingerprint, fingerprint(discoverFiles(config.docsDir)));
}

export async function buildIndex(config) {
  // Extract + chunk every supported file. Returns { chunks, fileCount }.
  const files = discoverFiles(config.docsDir);
  const chunks = [];
  for (const filePath of files) {
    const pages = await extractPages(filePath);
    chunks.push(...chunkPages(pages));
  }

  fs.mkdirSync(config.cacheDir, { recursive: true });
  fs.writeFileSync(
    indexPath(config),
    JSON.stringify({ fingerprint: fingerprint(files), chunks }),
    "utf-8"
  );
  return { chunks, fileCount: files.length };
}

export function loadChunks(config) {
  const data = JSON.parse(fs.readFileSync(indexPath(config), "utf-8"));
  return data.chunks;
}
