"""
Quality Critic Agent — coverage scoring, staleness detection, gap analysis.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from agents.base_agent import BaseAgent
from db.models import AgentTask, Document, Chunk

logger = structlog.get_logger()


class QualityCriticAgent(BaseAgent):
    name = "quality_critic"

    async def execute(self, task: AgentTask, db: AsyncSession) -> dict:
        project_id = str(task.project_id)

        # Count total public symbols
        total_symbols = await db.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.project_id == project_id,
                Chunk.chunk_type.in_(["function", "class"]),
                Chunk.is_public == True,
            )
        ) or 0

        # Count symbols with docstrings (symbol_name not null + chunk has docstring marker)
        documented_chunks = await db.scalar(
            select(func.count(Chunk.id)).where(
                Chunk.project_id == project_id,
                Chunk.chunk_type.in_(["function", "class"]),
                Chunk.is_public == True,
                Chunk.content.contains('"""'),
            )
        ) or 0

        coverage_score = (documented_chunks / total_symbols) if total_symbols > 0 else 0.0

        # Find stale generated documents
        stale_docs_result = await db.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.status == "stale",
            )
        )
        stale_docs = stale_docs_result.scalars().all()

        # Find missing doc types
        generated_types_result = await db.execute(
            select(Document.generated_type).where(
                Document.project_id == project_id,
                Document.doc_type == "generated",
            )
        )
        existing_types = {row[0] for row in generated_types_result.fetchall() if row[0]}
        all_types = {"readme", "api_reference", "architecture", "getting_started"}
        missing_types = list(all_types - existing_types)

        # Update project coverage score
        from db.models import Project
        from sqlalchemy import update
        await db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(doc_coverage_score=coverage_score)
        )
        await db.commit()

        return {
            "coverage_score": round(coverage_score, 3),
            "total_symbols": total_symbols,
            "documented_symbols": documented_chunks,
            "stale_documents": [str(d.id) for d in stale_docs],
            "missing_doc_types": missing_types,
            "gaps": {
                "has_readme": "readme" in existing_types,
                "has_api_reference": "api_reference" in existing_types,
                "has_architecture": "architecture" in existing_types,
                "has_getting_started": "getting_started" in existing_types,
            },
        }
