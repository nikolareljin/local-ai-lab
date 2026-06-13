# Lesson 3 — Node.js port

Hybrid retrieval (BM25 + a semantic stand-in, fused with RRF), dependency-free and offline. ESM,
Node 18+.

## Run

```bash
cd lessons/03-hybrid-retrieval-reranking/node
./run.sh            # or: node hybrid_demo.mjs   (or: npm start)
```

No packages to install. Reads the shared corpus in `../data`.

## Expected output

```
Query: "error E_4096"
  BM25 (lexical):   ['error_codes.md', 'power_issues.md', 'setup.md']
  Semantic (stand): ['error_codes.md', 'power_issues.md', 'setup.md']
  Hybrid (RRF):     ['error_codes.md', 'power_issues.md', 'setup.md']

Query: "my device won't turn on"
  BM25 (lexical):   ['power_issues.md', 'setup.md', 'error_codes.md']
  Semantic (stand): ['power_issues.md', 'error_codes.md', 'setup.md']
  Hybrid (RRF):     ['power_issues.md', 'error_codes.md', 'setup.md']
```

Identical to the Python and .NET ports — same algorithm, three languages.
