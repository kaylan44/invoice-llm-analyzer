"""Text embeddings with Gemini, for retrieval in pgvector.

gemini-embedding-2 has no ``task_type`` parameter: the task goes in the text itself, with
the prefixes from https://ai.google.dev/gemini-api/docs/embeddings (asymmetric retrieval):

    query:    "task: search result | query: {text}"
    document: "title: {title} | text: {text}"   ("title: none" when there is no title)

Queries and documents are embedded differently on purpose: a short query ("toner HP")
must land near a longer document describing the category.

Two traps of the SDK, checked with real calls on 2026-11-27:
- ``contents=["a", "b"]`` returns ONE embedding for both texts together. One vector per
  text needs one ``Content`` per text.
- Vectors truncated to 768 dimensions come back normalized (norm 1), so cosine distance
  and inner product rank the same way.
"""

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from google.genai import types

DEFAULT_MODEL = "gemini-embedding-2"
DIMENSIONS = 768  # fixed by the migrations: vector(768)
BATCH_SIZE = 50

Embedder = Callable[[Sequence[str]], list[list[float]]]


def query_text(text: str) -> str:
    return f"task: search result | query: {text}"


def document_text(text: str, title: str | None = None) -> str:
    return f"title: {title or 'none'} | text: {text}"


def embedding_model() -> str:
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)


def embed(texts: Sequence[str], *, client: Any, model: str | None = None) -> list[list[float]]:
    """One 768-dim vector per text, in order. Texts must already carry their prefix."""
    model = model or embedding_model()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        response = client.models.embed_content(
            model=model,
            contents=[types.Content(parts=[types.Part(text=t)]) for t in batch],
            config=types.EmbedContentConfig(output_dimensionality=DIMENSIONS),
        )
        if len(response.embeddings) != len(batch):
            raise RuntimeError(f"asked {len(batch)} embeddings, got {len(response.embeddings)}")
        vectors.extend(list(e.values) for e in response.embeddings)
    return vectors


class CachedEmbedder:
    """Embedder with an on-disk cache (JSON lines), so evals do not re-embed the same texts.

    The key includes the model and the size: changing either never reuses a stale vector.
    """

    def __init__(self, client: Any, cache_path: Path, model: str | None = None) -> None:
        self.client = client
        self.model = model or embedding_model()
        self.path = cache_path
        self.cache: dict[str, list[float]] = {}
        self.calls = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                entry = json.loads(line)
                self.cache[entry["key"]] = entry["vector"]

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model}|{DIMENSIONS}|{text}".encode()).hexdigest()

    def __call__(self, texts: Sequence[str]) -> list[list[float]]:
        missing = list(dict.fromkeys(t for t in texts if self._key(t) not in self.cache))
        if missing:
            self.calls += 1
            vectors = embed(missing, client=self.client, model=self.model)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                for text, vector in zip(missing, vectors, strict=True):
                    key = self._key(text)
                    self.cache[key] = vector
                    f.write(json.dumps({"key": key, "vector": vector}) + "\n")
        return [self.cache[self._key(t)] for t in texts]
