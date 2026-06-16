"""Build, cache, and load the document index.

The index is just a JSON file of chunks (plus metadata) under .localrag/. When
embeddings mode is on, vectors are cached alongside it as a .npz file. Files are
fingerprinted by (path, mtime, size) so re-indexing only happens when something
changed — this is the "drop a file in docs/ and ask again" loop.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from .chunk import Chunk, chunk_pages
from .config import Config
from .extract import discover_files, extract_pages


def _fingerprint(files: List[Path]) -> List[dict]:
    fp = []
    for p in files:
        st = p.stat()
        fp.append({"path": str(p), "mtime": int(st.st_mtime), "size": st.st_size})
    return fp


def _index_path(config: Config) -> Path:
    return config.cache_dir / "index.json"


def _vectors_path(config: Config) -> Path:
    return config.cache_dir / "vectors.npz"


def is_stale(config: Config) -> bool:
    """True if the cache is missing or the docs folder changed since last build."""
    index_path = _index_path(config)
    if not index_path.exists():
        return True
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return True
    return data.get("fingerprint") != _fingerprint(discover_files(config.docs_dir))


def build_index(config: Config) -> Tuple[List[Chunk], int]:
    """Extract + chunk every supported file. Returns (chunks, file_count)."""
    files = discover_files(config.docs_dir)
    chunks: List[Chunk] = []
    for path in files:
        chunks.extend(chunk_pages(extract_pages(path)))

    config.cache_dir.mkdir(parents=True, exist_ok=True)
    _index_path(config).write_text(
        json.dumps({"fingerprint": _fingerprint(files), "chunks": chunks}, ensure_ascii=False),
        encoding="utf-8",
    )
    # Vectors (if any) are rebuilt lazily by the retriever; drop a stale cache now.
    if _vectors_path(config).exists():
        _vectors_path(config).unlink()
    return chunks, len(files)


def load_chunks(config: Config) -> List[Chunk]:
    data = json.loads(_index_path(config).read_text(encoding="utf-8"))
    return data["chunks"]


def load_vectors(config: Config):
    import numpy as np

    path = _vectors_path(config)
    if not path.exists():
        return None
    with np.load(path) as npz:
        return npz["vectors"]


def save_vectors(config: Config, vectors) -> None:
    import numpy as np

    config.cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez(_vectors_path(config), vectors=np.asarray(vectors, dtype="float32"))
