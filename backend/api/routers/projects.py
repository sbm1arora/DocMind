import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from api.middleware.auth import get_current_user, get_db
from api.schemas.projects import ProjectCreate, ProjectOut, RepoItem
from api.services.projects_service import (
    create_project,
    delete_project,
    get_project,
    list_available_repos,
    list_projects,
)
from db.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/available-repos", response_model=list[RepoItem])
async def get_available_repos(
    current_user: User = Depends(get_current_user),
):
    """List all GitHub repos the current user has access to."""
    return await list_available_repos(current_user)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def connect_project(
    request: Request,
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Connect a GitHub repo — registers webhook and queues full ingestion."""
    redis: Redis = request.app.state.redis
    project = await create_project(
        db=db,
        redis=redis,
        user=current_user,
        repo_full_name=body.repo_full_name,
        branch=body.branch,
    )
    return project


@router.get("", response_model=list[ProjectOut])
async def get_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all projects for the current user."""
    return await list_projects(db, current_user)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project_status(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single project by ID — used by frontend for status polling."""
    return await get_project(db, current_user, project_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a project — removes GitHub webhook and cascades all data."""
    await delete_project(db, current_user, project_id)
    return JSONResponse(status_code=204, content=None)
