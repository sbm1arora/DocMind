import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_current_user, get_db
from api.schemas.queries import QueryRequest, QueryResponse
from api.services.projects_service import get_project
from db.models import User, Query
from rag.pipeline import run_rag_pipeline
from shared.exceptions import ValidationError

logger = structlog.get_logger()

router = APIRouter(tags=["queries"])


@router.post(
    "/projects/{project_id}/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
)
async def query_project(
    project_id: UUID,
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run a natural language query against an indexed project."""
    if not body.query.strip():
        raise ValidationError("Query cannot be empty")

    # Verify project exists and belongs to user
    project = await get_project(db, current_user, project_id)

    if project.status != "indexed":
        raise ValidationError(f"Project is not indexed yet (status: {project.status})")

    result = await run_rag_pipeline(
        query=body.query,
        project_id=str(project_id),
        db=db,
    )

    # Log query
    query_log = Query(
        project_id=str(project_id),
        user_id=str(current_user.id),
        channel=body.channel,
        query_text=body.query,
        response_text=result["answer"],
        chunks_used=result["chunks_used"],
        confidence_score=result["confidence"],
        latency_ms=result["latency_ms"],
    )
    db.add(query_log)
    await db.commit()

    return QueryResponse(
        answer=result["answer"],
        citations=result["citations"],
        confidence=result["confidence"],
        follow_ups=result["follow_ups"],
        latency_ms=result["latency_ms"],
    )
