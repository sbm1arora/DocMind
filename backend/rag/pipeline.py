"""
RAG pipeline orchestrator.

query → dense search + sparse search → RRF fusion → Cohere rerank → Claude generation
"""

import time
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from shared.constants import RAG_TOP_K_DENSE, RAG_TOP_K_SPARSE, RAG_TOP_K_RERANK
from rag.dense_search import dense_search
from rag.sparse_search import sparse_search
from rag.fusion import reciprocal_rank_fusion
from rag.reranker import rerank
from rag.generator import generate_answer

logger = structlog.get_logger()


async def run_rag_pipeline(
    query: str,
    project_id: str,
    db: AsyncSession,
) -> dict:
    """
    Full RAG pipeline.

    Returns:
        {
            "answer": str,
            "citations": list[str],
            "confidence": float,
            "follow_ups": list[str],
            "chunks_used": list[str],   # chunk IDs
            "latency_ms": int,
        }
    """
    start = time.monotonic()

    # 1. Retrieve — dense + sparse in parallel
    import asyncio
    dense_task = asyncio.create_task(dense_search(query, project_id, top_k=RAG_TOP_K_DENSE))
    sparse_task = asyncio.create_task(sparse_search(query, project_id, db, top_k=RAG_TOP_K_SPARSE))
    dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)

    logger.info("rag.retrieved", dense=len(dense_results), sparse=len(sparse_results))

    # 2. Fuse
    fused = reciprocal_rank_fusion(dense_results, sparse_results, top_k=RAG_TOP_K_DENSE)

    # 3. Rerank
    reranked = await rerank(query, fused, top_k=RAG_TOP_K_RERANK)

    # 4. Generate
    result = await generate_answer(query, reranked)

    latency_ms = int((time.monotonic() - start) * 1000)
    chunk_ids = [r["id"] for r in reranked]

    logger.info("rag.complete", confidence=result["confidence"], latency_ms=latency_ms)

    return {
        **result,
        "chunks_used": chunk_ids,
        "latency_ms": latency_ms,
    }
