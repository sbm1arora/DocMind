"""
Agent task endpoints.

POST /api/v1/projects/{id}/documents/generate — queue writer agent task
POST /api/v1/projects/{id}/documents/create-pr — trigger PR creation
GET  /api/v1/agents/tasks/{task_id}            — poll task status
"""

import json
import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from api.middleware.auth import get_current_user, get_db
from api.services.projects_service import get_project
from api.utils.encryption import decrypt_token
from db.models import AgentTask, Document, User, Project
from shared.constants import REDIS_CHANNEL_AGENTS
from shared.exceptions import NotFoundError, AuthorizationError, ValidationError

logger = structlog.get_logger()

router = APIRouter(tags=["agents"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    doc_types: list[str] = ["readme", "api_reference", "architecture", "getting_started"]


class CreatePRRequest(BaseModel):
    document_ids: list[str]


class AgentTaskOut(BaseModel):
    id: str
    task_type: str
    status: str
    output: dict | None
    progress: dict | None

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _queue_task(
    db: AsyncSession,
    redis: Redis,
    project_id: str,
    task_type: str,
    agent_name: str,
    input_data: dict,
) -> AgentTask:
    task = AgentTask(
        project_id=project_id,
        task_type=task_type,
        status="queued",
        input=input_data,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    await redis.publish(
        REDIS_CHANNEL_AGENTS,
        json.dumps({"agent": agent_name, "task_id": str(task.id)}),
    )
    logger.info("agents.task_queued", task_id=str(task.id), agent=agent_name)
    return task


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/documents/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_documents(
    project_id: UUID,
    body: GenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a writer agent task to generate documentation for the project."""
    project = await get_project(db, current_user, project_id)
    if project.status != "indexed":
        raise ValidationError(f"Project must be indexed before generating docs (status: {project.status})")

    redis: Redis = request.app.state.redis
    task = await _queue_task(
        db, redis,
        project_id=str(project_id),
        task_type="generate_docs",
        agent_name="writer",
        input_data={"doc_types": body.doc_types},
    )
    return {"task_id": str(task.id), "status": "queued"}


@router.post("/projects/{project_id}/documents/create-pr", status_code=status.HTTP_202_ACCEPTED)
async def create_docs_pr(
    project_id: UUID,
    body: CreatePRRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger PR creation for specified generated documents."""
    project = await get_project(db, current_user, project_id)

    # Verify all document IDs belong to this project
    docs_result = await db.execute(
        select(Document).where(
            Document.id.in_(body.document_ids),
            Document.project_id == str(project_id),
        )
    )
    docs = docs_result.scalars().all()
    if len(docs) != len(body.document_ids):
        raise ValidationError("One or more document IDs are invalid or not in this project")

    redis: Redis = request.app.state.redis
    task = await _queue_task(
        db, redis,
        project_id=str(project_id),
        task_type="create_pr",
        agent_name="pr_creator",
        input_data={"document_ids": body.document_ids},
    )
    return {"task_id": str(task.id), "status": "queued"}


@router.get("/agents/tasks/{task_id}", response_model=AgentTaskOut)
async def get_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Poll agent task status and output."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError(f"Task {task_id} not found")

    # Verify user owns the project this task belongs to
    project = await db.get(Project, task.project_id)
    if not project or project.user_id != current_user.id:
        raise AuthorizationError("Access denied")

    return AgentTaskOut(
        id=str(task.id),
        task_type=task.task_type,
        status=task.status,
        output=task.output,
        progress=task.progress,
    )
