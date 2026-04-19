"""
Cohere rerank-v3.5 — takes top-20 fused results, returns top-5.
"""

import structlog
import cohere

from api.config import settings
from shared.constants import RAG_TOP_K_RERANK, RERANK_MODEL

logger = structlog.get_logger()

_client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)


async def rerank(query: str, results: list[dict], top_k: int = RAG_TOP_K_RERANK) -> list[dict]:
    """
    Rerank fused results using Cohere rerank-v3.5.

    results: list of {"id": str, "score": float, "payload": {"content": str, ...}}
    Returns top_k results sorted by rerank score, with original payload preserved.
    """
    if not results:
        return []

    documents = [r["payload"].get("content", "") for r in results]

    try:
        response = await _client.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=min(top_k, len(documents)),
        )
        reranked = []
        for item in response.results:
            original = results[item.index]
            reranked.append({
                "id": original["id"],
                "score": item.relevance_score,
                "payload": original["payload"],
            })
        return reranked

    except Exception as e:
        logger.warning("reranker.failed", error=str(e))
        # Fall back to pre-rerank order
        return results[:top_k]
