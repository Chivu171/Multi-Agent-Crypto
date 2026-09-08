# rag/retriever.py

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from rag.chunking import chunk_text
from utils.embeddings import embed_text, embed_texts
from utils.scoring import cosine_similarity


class Retriever:
    """In-memory vector store: chunk -> embed -> cosine-similarity top-k search.

    No external vector DB — documents and their embeddings are kept in a plain
    Python list and can be persisted to / restored from a JSON file.
    """

    def __init__(self):
        self._chunks: List[Dict[str, Any]] = []

    def ingest(self, text: str, source: str, chunk_size: int = 800, overlap: int = 100) -> int:
        """Chunk `text`, embed each chunk, and add it to the store. Returns the number of chunks added."""
        pieces = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        if not pieces:
            return 0

        vectors = embed_texts(pieces)
        for i, (piece, vector) in enumerate(zip(pieces, vectors)):
            self._chunks.append({
                "id": f"{source}::{i}",
                "content": piece,
                "source": source,
                "embedding": vector,
            })
        return len(pieces)

    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Return the top-k chunks most similar to `query_text`, sorted by descending similarity."""
        if not self._chunks:
            return []

        query_vector = embed_text(query_text)
        scored = [
            {**{k: v for k, v in c.items() if k != "embedding"}, "score": cosine_similarity(query_vector, c["embedding"])}
            for c in self._chunks
        ]
        scored.sort(key=lambda c: c["score"], reverse=True)
        return scored[:top_k]

    def __len__(self) -> int:
        return len(self._chunks)

    def save(self, path: str) -> None:
        """Persist the store to a JSON file (embeddings included) so it can be reloaded without re-embedding."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        serializable = [
            {**{k: v for k, v in c.items() if k != "embedding"}, "embedding": c["embedding"].tolist()}
            for c in self._chunks
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Retriever":
        """Restore a store previously written by `save`."""
        retriever = cls()
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        retriever._chunks = [
            {**c, "embedding": np.array(c["embedding"], dtype=np.float32)}
            for c in raw
        ]
        return retriever
