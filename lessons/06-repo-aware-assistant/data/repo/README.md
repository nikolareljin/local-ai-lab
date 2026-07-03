# notes-api

A tiny local notes service. Notes are split into passages, indexed by
keyword, and ranked against a query so you can search offline.

## Layout

- `src/chunker.py` splits a note into passages.
- `src/retriever.py` ranks passages against a query.
- `src/providers.py` registers the embedding backends retrieval can use.
- `tests/test_retriever.py` pins ranking and tie-breaking.
- `scripts/reindex.sh` rebuilds the index from scratch.

## Configuration

Point `NOTES_DB` at the index file. Pick a backend with `EMBED_PROVIDER`.
