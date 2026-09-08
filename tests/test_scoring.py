import numpy as np

from utils.scoring import cosine_similarity


def test_identical_vectors_have_similarity_one():
    v = np.array([1.0, 2.0, 3.0])
    assert cosine_similarity(v, v) == 1.0


def test_orthogonal_vectors_have_similarity_zero():
    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert cosine_similarity(a, b) == 0.0


def test_opposite_vectors_have_similarity_negative_one():
    a = np.array([1.0, 0.0])
    b = np.array([-1.0, 0.0])
    assert cosine_similarity(a, b) == -1.0


def test_zero_vector_returns_zero():
    a = np.array([0.0, 0.0])
    b = np.array([1.0, 1.0])
    assert cosine_similarity(a, b) == 0.0
