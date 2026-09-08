import pytest

from rag.chunking import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_short_text_returns_single_chunk():
    assert chunk_text("hello world", chunk_size=100, overlap=10) == ["hello world"]


def test_long_text_splits_into_multiple_chunks():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_consecutive_chunks_overlap():
    text = "0123456789" * 10  # 100 chars
    chunks = chunk_text(text, chunk_size=40, overlap=10)
    # last 10 chars of chunk[0] should reappear at the start of chunk[1]
    assert chunks[0][-10:] == chunks[1][:10]


def test_rejects_invalid_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=0)


def test_rejects_overlap_not_smaller_than_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=10, overlap=10)
    with pytest.raises(ValueError):
        chunk_text("text", chunk_size=10, overlap=-1)
