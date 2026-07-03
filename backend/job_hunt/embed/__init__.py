"""Embeddings — text → vector for pgvector semantic search."""
from __future__ import annotations

from job_hunt.embed.embedder import EMBED_DIM, embed_text

__all__ = ["embed_text", "EMBED_DIM"]
