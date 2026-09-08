import json
from unittest.mock import patch

import numpy as np

from rag.retriever import Retriever


def _keyword_vector(text: str) -> np.ndarray:
    """Deterministic fake embedding: counts of 'cat' and 'dog' tokens. No network calls."""
    lower = text.lower()
    return np.array([float(lower.count("cat")), float(lower.count("dog"))], dtype=np.float32)


def _fake_embed_texts(texts):
    return [_keyword_vector(t) for t in texts]


def _fake_embed_text(text):
    return _keyword_vector(text)


@patch("rag.retriever.embed_texts", side_effect=_fake_embed_texts)
def test_ingest_chunks_and_embeds_text(mock_embed_texts):
    retriever = Retriever()
    added = retriever.ingest("cat cat cat " * 50, source="doc1", chunk_size=100, overlap=20)

    assert added > 0
    assert len(retriever) == added
    assert mock_embed_texts.called


@patch("rag.retriever.embed_text", side_effect=_fake_embed_text)
@patch("rag.retriever.embed_texts", side_effect=_fake_embed_texts)
def test_query_ranks_most_similar_chunk_first(mock_embed_texts, mock_embed_text):
    retriever = Retriever()
    retriever.ingest("all about cats and kittens", source="cats.txt", chunk_size=1000, overlap=0)
    retriever.ingest("all about dogs and puppies", source="dogs.txt", chunk_size=1000, overlap=0)

    results = retriever.query("cat", top_k=2)

    assert results[0]["source"] == "cats.txt"
    assert results[0]["score"] > results[1]["score"]


@patch("rag.retriever.embed_text", side_effect=_fake_embed_text)
def test_query_on_empty_store_returns_empty_list(mock_embed_text):
    retriever = Retriever()
    assert retriever.query("anything") == []
    mock_embed_text.assert_not_called()


@patch("rag.retriever.embed_texts", side_effect=_fake_embed_texts)
def test_save_and_load_round_trip(mock_embed_texts, tmp_path):
    retriever = Retriever()
    retriever.ingest("cat cat dog", source="doc1", chunk_size=1000, overlap=0)

    path = tmp_path / "index.json"
    retriever.save(str(path))
    restored = Retriever.load(str(path))

    assert len(restored) == len(retriever)
    assert restored._chunks[0]["content"] == retriever._chunks[0]["content"]
    assert np.array_equal(restored._chunks[0]["embedding"], retriever._chunks[0]["embedding"])
