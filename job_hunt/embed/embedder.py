"""Text → embedding vector, via a pluggable provider (like the LLM registry).

  EMBED_PROVIDER = ollama (default) | stub
  EMBED_MODEL    = nomic-embed-text (Ollama; 768-dim)
  EMBED_DIM      = 768  (must match the vector(...) column in migration 0008)

The `stub` provider is deterministic (hash → unit vector) so semantic search is testable
end-to-end without pulling an embedding model.
"""
from __future__ import annotations

import hashlib
import math
import os
import struct

import httpx

from job_hunt.llm.providers.ollama import OLLAMA_URL

EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")


def _stub_embed(text: str, dim: int) -> list[float]:
    """Deterministic pseudo-embedding: expand a hash into a unit vector."""
    values: list[float] = []
    counter = 0
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    while len(values) < dim:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for i in range(0, len(block), 4):
            if len(values) >= dim:
                break
            values.append(struct.unpack(">I", block[i : i + 4])[0] / 2**32 - 0.5)
        counter += 1
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def _ollama_embed(text: str) -> list[float]:
    resp = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]


def embed_text(text: str) -> list[float]:
    """Return an embedding for `text` using the configured provider."""
    provider = os.getenv("EMBED_PROVIDER", "ollama").lower()
    if provider == "stub":
        return _stub_embed(text, EMBED_DIM)
    return _ollama_embed(text)
