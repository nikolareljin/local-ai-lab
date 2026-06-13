# Lesson 3 — Python port

Hybrid retrieval (BM25 + a semantic stand-in, fused with RRF), dependency-free and offline.

## Run

```bash
cd lessons/03-hybrid-retrieval-reranking/python
python hybrid_demo.py        # prints BM25 / semantic / hybrid rankings for two queries
python -m pytest test_hybrid.py -q
```

No packages to install — standard library only. Reads the shared corpus in `../data`.

## Expected output

```
Query: 'error E_4096'
  BM25 (lexical):   ['error_codes.md', 'power_issues.md', 'setup.md']
  Semantic (stand): ['error_codes.md', 'power_issues.md', 'setup.md']
  Hybrid (RRF):     ['error_codes.md', 'power_issues.md', 'setup.md']

Query: "my device won't turn on"
  BM25 (lexical):   ['power_issues.md', 'setup.md', 'error_codes.md']
  Semantic (stand): ['power_issues.md', 'error_codes.md', 'setup.md']
  Hybrid (RRF):     ['power_issues.md', 'error_codes.md', 'setup.md']
```

The Node and .NET ports produce the same rankings.
