// Extract plain text from supported document types.
//
// Returns a list of "pages": objects with `text`, `page_number` and `source`.
// For formats without real pages (DOCX/TXT/MD) the whole document is one page.
// Mirrors localrag/extract.py. PARITY NOTE: pdf-parse returns whole-document
// text rather than per-page text, so PDFs emit a single page (page_number 1)
// instead of one page per physical PDF page.

import fs from "node:fs";
import path from "node:path";

export const SUPPORTED_EXTS = new Set([".pdf", ".docx", ".txt", ".md", ".markdown"]);

function readTextFile(filePath) {
  // Node reads UTF-8 by default; latin-1 fallback is unnecessary for utf-8 files.
  return fs.readFileSync(filePath, "utf-8");
}

async function extractPdf(filePath) {
  // pdf-parse ships as CommonJS; load it lazily so the dep is only needed for PDFs.
  const { default: pdfParse } = await import("pdf-parse");
  const data = await pdfParse(fs.readFileSync(filePath));
  const text = (data.text || "").trim();
  if (!text) return [];
  return [{ source: path.basename(filePath), page_number: 1, text }];
}

async function extractDocx(filePath) {
  const { default: mammoth } = await import("mammoth");
  const { value } = await mammoth.extractRawText({ path: filePath });
  const text = (value || "").trim();
  if (!text) return [];
  return [{ source: path.basename(filePath), page_number: 1, text }];
}

export async function extractPages(filePath) {
  // Extract text from a single file. Unsupported types return an empty list.
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".pdf") return extractPdf(filePath);
  if (ext === ".docx") return extractDocx(filePath);
  if (ext === ".txt" || ext === ".md" || ext === ".markdown") {
    const text = readTextFile(filePath).trim();
    return text ? [{ source: path.basename(filePath), page_number: 1, text }] : [];
  }
  return [];
}

function walk(dir, acc) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full, acc);
    } else if (entry.isFile() && SUPPORTED_EXTS.has(path.extname(full).toLowerCase())) {
      acc.push(full);
    }
  }
}

export function discoverFiles(docsDir) {
  // Find all supported files under the docs directory (recursively), sorted.
  if (!fs.existsSync(docsDir)) return [];
  const acc = [];
  walk(docsDir, acc);
  acc.sort();
  return acc;
}
