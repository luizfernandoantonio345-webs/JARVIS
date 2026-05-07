from __future__ import annotations

import hashlib
import math
from functools import lru_cache
from typing import List

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
FALLBACK_DIM = 384


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def _fallback_embedding(text: str) -> List[float]:
    vec = [0.0] * FALLBACK_DIM
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % FALLBACK_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def get_embedding(text: str) -> List[float]:
    try:
        model = _load_model()
        return [float(v) for v in model.encode(text, normalize_embeddings=True)]
    except Exception:
        return _fallback_embedding(text)

