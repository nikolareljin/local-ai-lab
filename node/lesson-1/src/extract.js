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
const MAX_DOCX_XML_BYTES = 8 * 1024 * 1024;

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
  const [{ DOMParser }, { strFromU8, unzipSync }] = await Promise.all([
    import("@xmldom/xmldom"),
    import("fflate"),
  ]);
  let entries;
  let documentXmlTooLarge = false;
  try {
    entries = unzipSync(fs.readFileSync(filePath), {
      filter: (file) => {
        if (file.name !== "word/document.xml") return false;
        documentXmlTooLarge = file.originalSize > MAX_DOCX_XML_BYTES;
        return !documentXmlTooLarge;
      },
    });
  } catch {
    throw new Error(`Could not read DOCX archive: ${path.basename(filePath)}`);
  }
  if (documentXmlTooLarge) {
    throw new Error(`DOCX document XML exceeds the 8 MB limit: ${path.basename(filePath)}`);
  }
  const documentXml = entries["word/document.xml"];
  if (!documentXml) return [];

  let doc;
  try {
    doc = new DOMParser({
      onError: (level, message) => {
        if (level !== "warning") throw new Error(message);
      },
    }).parseFromString(strFromU8(documentXml), "application/xml");
  } catch {
    throw new Error(`Could not read DOCX document XML: ${path.basename(filePath)}`);
  }
  if (doc.getElementsByTagName("parsererror").length > 0) {
    throw new Error(`Could not read DOCX document XML: ${path.basename(filePath)}`);
  }
  const paragraphs = Array.from(doc.getElementsByTagName("w:p"));
  const text = paragraphs.map(docxNodeText).join("\n").trim();
  if (!text) return [];
  return [{ source: path.basename(filePath), page_number: 1, text }];
}

function docxNodeText(node) {
  if (node.nodeName === "w:t") return node.textContent || "";
  if (node.nodeName === "w:tab") return "\t";
  if (node.nodeName === "w:br" || node.nodeName === "w:cr") return "\n";
  return Array.from(node.childNodes || []).map(docxNodeText).join("");
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
