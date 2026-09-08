# rag/chunking.py

from typing import List


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Split `text` into overlapping character-based chunks.

    `chunk_size` and `overlap` are in characters. Chunks are trimmed and empty
    chunks are dropped. `overlap` must be smaller than `chunk_size`.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be >= 0 and < chunk_size")

    text = text.strip()
    if not text:
        return []

    chunks = []
    step = chunk_size - overlap
    for start in range(0, len(text), step):
        piece = text[start:start + chunk_size].strip()
        if piece:
            chunks.append(piece)
        if start + chunk_size >= len(text):
            break
    return chunks
