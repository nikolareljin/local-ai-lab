"""Chunking is implemented here: turn a note into passages."""


def chunk_lines(lines, size):
    """Group lines into fixed-size passages the retriever can rank."""
    passages = []
    for start in range(0, len(lines), size):
        passages.append(lines[start:start + size])
    return passages


def chunk_note(text, size=3):
    """Split a note into passages of `size` lines each."""
    return chunk_lines(text.splitlines(), size)
