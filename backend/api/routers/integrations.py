"""
Channel integrations — Slack and WhatsApp (Twilio) webhook endpoints.
"""

import json
import structlog
from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import PlainTextResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_db
from api.utils.hmac_utils import verify_slack_signature
from db.models import Integration, Project, Query
from rag.pipeline import run_rag_pipeline
from shared.exceptions import WebhookError

logger = structlog.get_logger()

router = APIRouter(prefix="/integrations", tags=["integrations"])

MAX_WHATSAPP_CHARS = 1500


def _format_for_whatsapp(answer: str, citations: list[str]) -> str:
    """Truncate + format answer for WhatsApp (max 1500 chars, plain text)."""
    # Replace markdown code blocks with plain text indentation
    import re
    text = re.sub(r"```[\w]*\n?", "", answer)
    text = re.sub(r"```", "", text)
    # Replace ## headings with bold
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    if citations:
        sources = "\n\nSources: " + " | ".join(citations[:3])
        text = text[:MAX_WHATSAPP_CHARS - len(sources)] + sources
    else:
        text = text[:MAX_WHATSAPP_CHARS]

    return text.strip()


# ── Slack ──────────────────────────────────────────────────────────────────────

@router.post("/slack/events")
async def slack_events(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_slack_signature: str = Header(default=""),
    x_slack_request_timestamp: str = Header(default=""),
):
    """Handle Slack app mentions and slash commands."""
    from api.config import settings

    body_bytes = await request.body()

    # Slack URL verification challenge
    try:
        data = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise WebhookError("Invalid JSON")

    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Validate Slack signature
    if settings.slack_signing_secret:
        if not verify_slack_signature(
            body_bytes, x_slack_request_timestamp, x_slack_signature, settings.slack_signing_secret
        ):
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    event = data.get("event", {})
    if event.get("type") != "app_mention":
        return {"status": "ignored"}

    # Strip bot mention from query text
    import re
    raw_text = event.get("text", "")
    query = re.sub(r"<@\w+>", "", raw_text).strip()
    channel = event.get("channel", "")
    thread_ts = event.get("ts", "")
    workspace_id = data.get("team_id", "")

    if not query:
        return {"status": "ignored"}

    # Find project mapped to this workspace
    result = await db.execute(
        select(Integration).where(
            Integration.platform == "slack",
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        logger.info("slack.no_integration", workspace=workspace_id)
        return {"status": "ignored"}

    project_id = str(integration.project_id)

    # Send immediate acknowledgment via Slack (fire-and-forget)
    redis: Redis = request.app.state.redis

    # Run RAG pipeline
    try:
        rag_result = await run_rag_pipeline(query=query, project_id=project_id, db=db)

        # Log query
        db.add(Query(
            project_id=project_id,
            channel="slack",
            query_text=query,
            response_text=rag_result["answer"],
            chunks_used=rag_result["chunks_used"],
            confidence_score=rag_result["confidence"],
            latency_ms=rag_result["latency_ms"],
        ))
        await db.commit()

        # Build Slack Block Kit response
        import httpx
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": rag_result["answer"][:2900]}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text":
                f"Sources: {' | '.join(f'`{c}`' for c in rag_result['citations'][:3])} · "
                f"Confidence: {rag_result['confidence']:.0%} · {rag_result['latency_ms']}ms"
            }]},
        ]

        slack_token = settings.slack_bot_token
        if slack_token:
            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {slack_token}"},
                    json={"channel": channel, "thread_ts": thread_ts, "blocks": blocks},
                )
    except Exception as e:
        logger.error("slack.rag_failed", error=str(e))

    return {"status": "ok"}


# ── WhatsApp / Twilio ──────────────────────────────────────────────────────────

@router.post("/whatsapp/webhook")
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Twilio WhatsApp inbound messages."""
    from api.config import settings
    import httpx

    form = await request.form()
    from_number = str(form.get("From", "")).replace("whatsapp:", "")
    body_text = str(form.get("Body", "")).strip()

    if not body_text:
        return PlainTextResponse("", status_code=200)

    # Find integration for this phone number
    result = await db.execute(
        select(Integration).where(Integration.platform == "whatsapp")
    )
    integration = result.scalar_one_or_none()

    if not integration:
        # Onboarding message
        reply = "Welcome to DocMind! Reply with your project name to get started."
        return PlainTextResponse(
            f'<?xml version="1.0"?><Response><Message>{reply}</Message></Response>',
            media_type="application/xml",
        )

    project_id = str(integration.project_id)

    try:
        rag_result = await run_rag_pipeline(query=body_text, project_id=project_id, db=db)

        reply = _format_for_whatsapp(rag_result["answer"], rag_result.get("citations", []))

        # Log query
        db.add(Query(
            project_id=project_id,
            channel="whatsapp",
            query_text=body_text,
            response_text=reply,
            chunks_used=rag_result["chunks_used"],
            confidence_score=rag_result["confidence"],
            latency_ms=rag_result["latency_ms"],
        ))
        await db.commit()

    except Exception as e:
        logger.error("whatsapp.rag_failed", error=str(e))
        reply = "Sorry, I encountered an error. Please try again."

    return PlainTextResponse(
        f'<?xml version="1.0"?><Response><Message>{reply}</Message></Response>',
        media_type="application/xml",
    )
