import json
import secrets
import structlog
import httpx
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from redis.asyncio import Redis

from api.config import settings
from api.utils.encryption import decrypt_token
from db.models import User, Project
from shared.exceptions import GitHubError, NotFoundError, AuthorizationError
from shared.constants import REDIS_CHANNEL_INGESTION

logger = structlog.get_logger()

GITHUB_API = "https://api.github.com"


def _github_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _decrypt_github_token(user: User) -> str:
    return decrypt_token(user.github_token_encrypted, user.github_token_iv)


async def list_available_repos(user: User) -> list[dict]:
    token = _decrypt_github_token(user)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GITHUB_API}/user/repos",
            headers=_github_headers(token),
            params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator"},
        )
    if response.status_code != 200:
        raise GitHubError(f"Failed to list repos: {response.status_code}")
    repos = response.json()
    return [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "private": r["private"],
            "language": r.get("language"),
            "updated_at": r["updated_at"],
        }
        for r in repos
    ]


async def _register_github_webhook(token: str, repo_full_name: str, secret: str) -> int:
    webhook_url = f"{settings.github_callback_url.rsplit('/api', 1)[0]}/api/v1/webhooks/github"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{GITHUB_API}/repos/{repo_full_name}/hooks",
            headers=_github_headers(token),
            json={
                "name": "web",
                "active": True,
                "events": ["push", "pull_request"],
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )
    if response.status_code not in (200, 201):
        raise GitHubError(f"Webhook registration failed: {response.status_code} — {response.text}")
    return response.json()["id"]


async def _delete_github_webhook(token: str, repo_full_name: str, webhook_id: int) -> None:
    async with httpx.AsyncClient() as client:
        await client.delete(
            f"{GITHUB_API}/repos/{repo_full_name}/hooks/{webhook_id}",
            headers=_github_headers(token),
        )


async def create_project(
    db: AsyncSession,
    redis: Redis,
    user: User,
    repo_full_name: str,
    branch: str = "main",
) -> Project:
    # Check not already connected
    existing = await db.execute(
        select(Project).where(
            Project.user_id == user.id,
            Project.repo_full_name == repo_full_name,
        )
    )
    if existing.scalar_one_or_none():
        raise GitHubError(f"Repo '{repo_full_name}' is already connected.")

    token = _decrypt_github_token(user)
    owner, repo_name = repo_full_name.split("/", 1)
    webhook_secret = secrets.token_hex(32)

    webhook_id = await _register_github_webhook(token, repo_full_name, webhook_secret)

    project = Project(
        user_id=user.id,
        repo_full_name=repo_full_name,
        repo_name=repo_name,
        repo_owner=owner,
        default_branch=branch,
        webhook_id=webhook_id,
        webhook_secret=webhook_secret,
        status="pending",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Publish ingestion job
    await redis.publish(
        REDIS_CHANNEL_INGESTION,
        json.dumps({"event": "ingestion:start", "project_id": str(project.id)}),
    )

    # Update status to indexing
    project.status = "indexing"
    await db.commit()
    await db.refresh(project)

    logger.info("project.created", project_id=str(project.id), repo=repo_full_name)
    return project


async def list_projects(db: AsyncSession, user: User) -> list[Project]:
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return list(result.scalars().all())


async def get_project(db: AsyncSession, user: User, project_id: UUID) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise NotFoundError(f"Project {project_id} not found")
    if project.user_id != user.id:
        raise AuthorizationError("Access denied")
    return project


async def delete_project(db: AsyncSession, user: User, project_id: UUID) -> None:
    project = await get_project(db, user, project_id)

    # Remove GitHub webhook
    if project.webhook_id:
        try:
            token = _decrypt_github_token(user)
            await _delete_github_webhook(token, project.repo_full_name, project.webhook_id)
        except Exception as e:
            logger.warning("project.webhook_delete_failed", error=str(e), project_id=str(project_id))

    await db.execute(delete(Project).where(Project.id == project_id))
    await db.commit()
    logger.info("project.deleted", project_id=str(project_id))
