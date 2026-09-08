from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import utils.embeddings as embeddings_module


@pytest.fixture(autouse=True)
def reset_client_cache():
    """_get_client caches a module-level client — reset it around every test."""
    embeddings_module._client = None
    yield
    embeddings_module._client = None


def test_get_client_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(embeddings_module, "GEMINI_API_KEY", None)
    with pytest.raises(RuntimeError):
        embeddings_module._get_client()


def test_embed_texts_empty_list_returns_empty_without_calling_client(monkeypatch):
    monkeypatch.setattr(embeddings_module, "GEMINI_API_KEY", "fake-key")
    with patch("utils.embeddings.genai.Client") as mock_client_cls:
        result = embeddings_module.embed_texts([])
    assert result == []
    mock_client_cls.assert_not_called()


def test_embed_texts_returns_one_vector_per_input(monkeypatch):
    monkeypatch.setattr(embeddings_module, "GEMINI_API_KEY", "fake-key")

    fake_embedding_a = MagicMock(values=[0.1, 0.2, 0.3])
    fake_embedding_b = MagicMock(values=[0.4, 0.5, 0.6])
    fake_response = MagicMock(embeddings=[fake_embedding_a, fake_embedding_b])

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = fake_response

    with patch("utils.embeddings.genai.Client", return_value=mock_client):
        vectors = embeddings_module.embed_texts(["hello", "world"])

    assert len(vectors) == 2
    assert np.allclose(vectors[0], [0.1, 0.2, 0.3])
    assert np.allclose(vectors[1], [0.4, 0.5, 0.6])


def test_embed_text_returns_single_vector(monkeypatch):
    monkeypatch.setattr(embeddings_module, "GEMINI_API_KEY", "fake-key")

    fake_embedding = MagicMock(values=[1.0, 2.0])
    fake_response = MagicMock(embeddings=[fake_embedding])

    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = fake_response

    with patch("utils.embeddings.genai.Client", return_value=mock_client):
        vector = embeddings_module.embed_text("hello")

    assert np.allclose(vector, [1.0, 2.0])


def test_client_is_cached_across_calls(monkeypatch):
    monkeypatch.setattr(embeddings_module, "GEMINI_API_KEY", "fake-key")
    with patch("utils.embeddings.genai.Client") as mock_client_cls:
        embeddings_module._get_client()
        embeddings_module._get_client()
    mock_client_cls.assert_called_once()
