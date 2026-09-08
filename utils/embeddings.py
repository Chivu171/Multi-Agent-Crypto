# utils/embeddings.py

from typing import List

import numpy as np
from google import genai

from utils.config import GEMINI_API_KEY, EMBEDDING_MODEL

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env to use the rag/ embeddings pipeline."
            )
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def embed_text(text: str) -> np.ndarray:
    """Embed a single string into a dense vector using the Gemini embedding model."""
    return embed_texts([text])[0]


def embed_texts(texts: List[str]) -> List[np.ndarray]:
    """Embed a batch of strings. Returns one numpy vector per input string, same order."""
    if not texts:
        return []
    client = _get_client()
    response = client.models.embed_content(model=EMBEDDING_MODEL, contents=texts)
    return [np.array(e.values, dtype=np.float32) for e in response.embeddings]
