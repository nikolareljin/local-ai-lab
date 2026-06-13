// Split extracted pages into overlapping chunks.
//
// Mirrors localrag/chunk.py exactly: target size with overlap, breaking on a
// sentence/word boundary near the limit instead of mid-word. Each chunk keeps
// its source + page so answers can cite where they came from.

function splitText(text, size, overlap) {
  text = text.split(/\s+/).filter(Boolean).join(" "); // normalize whitespace
  if (text.length <= size) {
    return text ? [text] : [];
  }

  const chunks = [];
  let start = 0;
  const n = text.length;
  while (start < n) {
    let end = Math.min(start + size, n);
    if (end < n) {
      // Prefer to break on a sentence boundary, then a space, near the limit.
      const window = text.slice(start, end);
      for (const sep of [". ", "! ", "? ", "\n", " "]) {
        const pos = window.lastIndexOf(sep);
        if (pos > Math.floor(size / 2)) {
          end = start + pos + sep.length;
          break;
        }
      }
    }
    const chunk = text.slice(start, end).trim();
    if (chunk) chunks.push(chunk);
    if (end >= n) break;
    start = Math.max(end - overlap, start + 1);
  }
  return chunks;
}

export function chunkPages(pages, size = 1000, overlap = 200) {
  const chunks = [];
  let index = 0;
  for (const page of pages) {
    for (const piece of splitText(page.text, size, overlap)) {
      chunks.push({
        source: page.source,
        page_number: page.page_number,
        chunk_index: index,
        text: piece,
      });
      index += 1;
    }
  }
  return chunks;
}
