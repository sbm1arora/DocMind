"""
GitHub webhook endpoint — validates HMAC signature, looks up project, publishes to Redis.
"""

import json
import structlog
from fastapi import APIRouter, Depends, Header, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_db
from api.schemas.webhooks import GitHubPushPayload
from api.utils.hmac_utils import verify_github_signature
from db.models import AuditLog, Project
from shared.constants import REDIS_CHANNEL_INGESTION
from shared.exceptions import WebhookError

logger = structlog.get_logger()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    """Receive GitHub push/PR events, validate HMAC, trigger incremental re-index."""
    body = await request.body()
    redis: Redis = request.app.state.redis

    # Only handle push events
    if x_github_event != "push":
        return {"status": "ignored", "event": x_github_event}

    # Parse payload to get repo name
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise WebhookError("Invalid JSON payload")

    repo_full_name = data.get("repository", {}).get("full_name", "")
    before_sha = data.get("before", "")
    after_sha = data.get("after", "")

    # Find project by repo name
    result = await db.execute(
        select(Project).where(
            Project.repo_full_name == repo_full_name,
            Project.status == "indexed",
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        # Acknowledge but ignore — repo not connected or not indexed
        logger.info("webhook.project_not_found", repo=repo_full_name)
        return {"status": "ignored", "reason": "project not found or not indexed"}

    # Validate HMAC signature
    if not verify_github_signature(body, x_hub_signature_256, project.webhook_secret or ""):
        # Log security event
        client_ip = request.client.host if request.client else "unknown"
        audit = AuditLog(
            project_id=str(project.id),
            action="webhook.invalid_signature",
            resource_type="webhook",
            ip_address=client_ip,
            metadata={"repo": repo_full_name, "event": x_github_event},
        )
        db.add(audit)
        await db.commit()
        logger.warning("webhook.invalid_signature", repo=repo_full_name, ip=client_ip)
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    # Skip no-op pushes (e.g. branch creation with no commits)
    if before_sha == "0" * 40 or after_sha == "0" * 40:
        return {"status": "ignored", "reason": "branch create/delete"}

    # Publish incremental ingestion job
    await redis.publish(
        REDIS_CHANNEL_INGESTION,
        json.dumps({
            "event": "ingestion:incremental",
            "project_id": str(project.id),
            "before_sha": before_sha,
            "after_sha": after_sha,
        }),
    )

    logger.info("webhook.dispatched", project_id=str(project.id), repo=repo_full_name)
    return {"status": "accepted", "project_id": str(project.id)}
