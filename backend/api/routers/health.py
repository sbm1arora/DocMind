import time
import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from db.database import check_db_health

logger = structlog.get_logger()

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    redis: str


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    """Service health check — verifies DB and Redis connectivity."""
    db_ok = await check_db_health()

    redis_ok = False
    try:
        await request.app.state.redis.ping()
        redis_ok = True
    except Exception as e:
        logger.warning("health.redis_fail", error=str(e))

    return HealthResponse(
        status="ok" if (db_ok and redis_ok) else "degraded",
        version="1.0.0",
        db="ok" if db_ok else "error",
        redis="ok" if redis_ok else "error",
    )
