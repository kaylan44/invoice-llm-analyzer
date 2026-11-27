"""Test doubles shared by the API tests."""

import hashlib
import math
from collections.abc import Sequence

from invoice_api.embeddings import DIMENSIONS
from invoice_api.text import normalize_text


def fake_embedder(texts: Sequence[str]) -> list[list[float]]:
    """Deterministic bag-of-words vectors: texts sharing words are close, others are not.

    Strips the Gemini prefixes ("... query: x", "... text: x") so a query and a document
    with the same words get the same vector. Enough to test the SQL, no network.
    """
    vectors = []
    for text in texts:
        body = text.split("query: ", 1)[-1].split("text: ", 1)[-1]
        vector = [0.0] * DIMENSIONS
        for word in normalize_text(body).split():
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        vectors.append([v / norm for v in vector])
    return vectors
