"""
Sparse full-text search — PostgreSQL tsvector search over chunks.content.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()


async def sparse_search(
    query: str,
    project_id: str,
    db: AsyncSession,
    top_k: int = 20,
) -> list[dict]:
    """PostgreSQL full-text search using tsvector ranking."""
    sql = text("""
        SELECT
            c.id::text AS id,
            c.content,
            c.chunk_type,
            c.symbol_name,
            c.document_id::text,
            d.file_path,
            ts_rank_cd(
                to_tsvector('english', c.content),
                plainto_tsquery('english', :query)
            ) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.project_id = :project_id
          AND to_tsvector('english', c.content) @@ plainto_tsquery('english', :query)
        ORDER BY score DESC
        LIMIT :top_k
    """)

    result = await db.execute(sql, {"query": query, "project_id": project_id, "top_k": top_k})
    rows = result.fetchall()

    return [
        {
            "id": row.id,
            "score": float(row.score),
            "payload": {
                "content": row.content,
                "chunk_type": row.chunk_type,
                "symbol_name": row.symbol_name,
                "document_id": row.document_id,
                "file_path": row.file_path,
                "project_id": project_id,
            },
        }
        for row in rows
    ]
