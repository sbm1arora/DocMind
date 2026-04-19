"""
OpenAI embedding client — batch text-embedding-3-large (2048 dimensions).

Handles rate limiting with exponential backoff (max 5 retries).
"""

import asyncio
import structlog
from openai import AsyncOpenAI

from api.config import settings
from shared.constants import EMBEDDING_MODEL, EMBEDDING_DIMENSIONS

logger = structlog.get_logger()

_client = AsyncOpenAI(api_key=settings.openai_api_key)

_MAX_BATCH = 100
_MAX_RETRIES = 5


async def _embed_batch(texts: list[str], attempt: int = 0) -> list[list[float]]:
    try:
        response = await _client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
    except Exception as e:
        if attempt >= _MAX_RETRIES:
            raise
        wait = 2 ** attempt
        logger.warning("embedder.retry", attempt=attempt, wait=wait, error=str(e))
        await asyncio.sleep(wait)
        return await _embed_batch(texts, attempt + 1)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts in batches. Returns embeddings in same order."""
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), _MAX_BATCH):
        batch = texts[i:i + _MAX_BATCH]
        embeddings = await _embed_batch(batch)
        all_embeddings.extend(embeddings)
        logger.info("embedder.batch_done", batch_start=i, batch_size=len(batch))

    return all_embeddings
