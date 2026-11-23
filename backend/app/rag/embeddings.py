"""Local embedding adapter (fastembed + BAAI/bge-small-en-v1.5, 384-dim, ONNX).

Only this module knows about the embedding library, like app/llm/client.py for the LLM.
The model (~130 MB) is downloaded on first use and cached by fastembed.
"""

import logging
from functools import lru_cache

log = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384

# bge models retrieve better when the *query* carries this instruction; documents do not.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class EmbeddingError(Exception):
    """The embedding model could not be loaded or run."""


@lru_cache
def _model():
    try:
        from fastembed import TextEmbedding

        log.info("loading embedding model %s", MODEL_NAME)
        return TextEmbedding(model_name=MODEL_NAME)
    except Exception as exc:
        raise EmbeddingError(f"Embedding model unavailable: {type(exc).__name__}") from exc


def embed_documents(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    try:
        return [[float(x) for x in v] for v in _model().embed(texts)]
    except EmbeddingError:
        raise
    except Exception as exc:
        raise EmbeddingError(f"Embedding failed: {type(exc).__name__}") from exc


def embed_query(text: str) -> list[float]:
    return embed_documents([_QUERY_PREFIX + text])[0]
