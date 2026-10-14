import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { strToU8, zipSync } from "fflate";

import { extractPages } from "../src/extract.js";

test("extractPages reads DOCX paragraphs, tabs, and line breaks", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "local-ai-lab-docx-"));
  const docxPath = path.join(dir, "sample.docx");
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>First paragraph</w:t></w:r></w:p>
        <w:p><w:r><w:t>Second</w:t><w:tab/><w:t>column</w:t><w:br/><w:t>line</w:t></w:r></w:p>
      </w:body>
    </w:document>`;
  fs.writeFileSync(docxPath, zipSync({ "word/document.xml": strToU8(xml) }));

  try {
    assert.deepEqual(await extractPages(docxPath), [{
      source: "sample.docx",
      page_number: 1,
      text: "First paragraph\nSecond\tcolumn\nline",
    }]);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("extractPages refuses an oversized DOCX document XML before extraction", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "local-ai-lab-docx-"));
  const docxPath = path.join(dir, "oversized.docx");
  fs.writeFileSync(docxPath, zipSync({
    "word/document.xml": strToU8("x".repeat(8 * 1024 * 1024 + 1)),
  }));

  try {
    await assert.rejects(extractPages(docxPath), /exceeds the 8 MB limit/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test("extractPages reports malformed DOCX document XML", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "local-ai-lab-docx-"));
  const docxPath = path.join(dir, "malformed.docx");
  const xml = `<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body><w:p></w:body>
  </w:document>`;
  fs.writeFileSync(docxPath, zipSync({ "word/document.xml": strToU8(xml) }));

  try {
    await assert.rejects(extractPages(docxPath), /Could not read DOCX document XML/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
