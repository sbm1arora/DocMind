"""
Qdrant client wrapper — upsert and delete document chunk vectors.

Collection: doc_chunks (created on first use if missing)
Vector size: 2048 (text-embedding-3-large)
Payload fields: project_id, document_id, chunk_id, file_path, chunk_type, symbol_name
"""

import structlog
from uuid import UUID
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)

from api.config import settings
from shared.constants import EMBEDDING_DIMENSIONS, QDRANT_COLLECTION

logger = structlog.get_logger()

_client = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


async def ensure_collection() -> None:
    """Create the Qdrant collection if it doesn't exist."""
    collections = await _client.get_collections()
    names = [c.name for c in collections.collections]
    if QDRANT_COLLECTION not in names:
        await _client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSIONS, distance=Distance.COSINE),
        )
        logger.info("vector_store.collection_created", collection=QDRANT_COLLECTION)


async def upsert_chunks(
    chunk_ids: list[str],
    embeddings: list[list[float]],
    payloads: list[dict],
) -> None:
    """Upsert a batch of chunk vectors with metadata payloads."""
    await ensure_collection()
    points = [
        PointStruct(id=chunk_id, vector=embedding, payload=payload)
        for chunk_id, embedding, payload in zip(chunk_ids, embeddings, payloads)
    ]
    await _client.upsert(collection_name=QDRANT_COLLECTION, points=points)
    logger.info("vector_store.upserted", count=len(points))


async def delete_by_project(project_id: str) -> None:
    """Delete all vectors for a project."""
    await _client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=Filter(
            must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
        ),
    )
    logger.info("vector_store.deleted_project", project_id=project_id)


async def delete_by_document(project_id: str, file_path: str) -> None:
    """Delete all vectors for a specific file within a project (used during incremental re-index)."""
    await _client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=Filter(
            must=[
                FieldCondition(key="project_id", match=MatchValue(value=project_id)),
                FieldCondition(key="file_path", match=MatchValue(value=file_path)),
            ]
        ),
    )
    logger.info("vector_store.deleted_document", project_id=project_id, file_path=file_path)


async def search(
    query_vector: list[float],
    project_id: str,
    top_k: int = 20,
) -> list[dict]:
    """Dense vector search within a project."""
    results = await _client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]
        ),
        limit=top_k,
        with_payload=True,
    )
    return [
        {"score": r.score, "payload": r.payload, "id": str(r.id)}
        for r in results
    ]
