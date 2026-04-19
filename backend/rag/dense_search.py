"""
Dense vector search — embeds query and searches Qdrant for nearest neighbours.
"""

from worker.ingestion.embedder import embed_texts
from worker.ingestion.vector_store import search


async def dense_search(query: str, project_id: str, top_k: int = 20) -> list[dict]:
    """Embed query and return top-k results from Qdrant with scores."""
    embeddings = await embed_texts([query])
    return await search(embeddings[0], project_id, top_k=top_k)
