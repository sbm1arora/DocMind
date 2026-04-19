import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import get_current_user, get_db
from api.schemas.auth import UserOut
from api.services.auth_service import complete_oauth, generate_oauth_redirect_url
from db.models import User

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github")
async def github_oauth_start(request: Request):
    """Redirect user to GitHub OAuth authorization page."""
    redis: Redis = request.app.state.redis
    redirect_url = await generate_oauth_redirect_url(redis)
    return RedirectResponse(url=redirect_url)


@router.get("/github/callback")
async def github_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub OAuth callback, issue JWT, redirect to frontend."""
    redis: Redis = request.app.state.redis
    user, jwt = await complete_oauth(code=code, state=state, redis=redis, db=db)
    frontend_url = request.app.state.settings.frontend_url
    logger.info("auth.login_complete", user_id=str(user.id))
    return RedirectResponse(url=f"{frontend_url}/dashboard?token={jwt}")


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return current_user
