import secrets
import structlog
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis

from api.config import settings
from api.utils.jwt_utils import create_access_token
from api.utils.encryption import encrypt_token
from db.models import User
from shared.exceptions import AuthenticationError, GitHubError
from shared.constants import REDIS_PREFIX_SESSION

logger = structlog.get_logger()

GITHUB_OAUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_SCOPES = "repo,read:org"
STATE_TTL = 600  # 10 minutes


async def generate_oauth_redirect_url(redis: Redis) -> str:
    state = secrets.token_urlsafe(32)
    await redis.setex(f"{REDIS_PREFIX_SESSION}state:{state}", STATE_TTL, "valid")
    params = (
        f"client_id={settings.github_client_id}"
        f"&redirect_uri={settings.github_callback_url}"
        f"&scope={GITHUB_SCOPES}"
        f"&state={state}"
    )
    return f"{GITHUB_OAUTH_URL}?{params}"


async def validate_oauth_state(redis: Redis, state: str) -> None:
    key = f"{REDIS_PREFIX_SESSION}state:{state}"
    val = await redis.get(key)
    if not val:
        raise AuthenticationError("Invalid or expired OAuth state")
    await redis.delete(key)


async def exchange_code_for_token(code: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_callback_url,
            },
        )
    if response.status_code != 200:
        raise GitHubError(f"Token exchange failed: {response.status_code}")
    data = response.json()
    access_token = data.get("access_token")
    if not access_token:
        raise GitHubError(f"No access_token in response: {data.get('error_description', data)}")
    return access_token


async def fetch_github_user(github_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            GITHUB_USER_URL,
            headers={"Authorization": f"Bearer {github_token}", "Accept": "application/json"},
        )
    if response.status_code != 200:
        raise GitHubError(f"GitHub user fetch failed: {response.status_code}")
    return response.json()


async def upsert_user(db: AsyncSession, github_token: str, github_user: dict) -> User:
    github_id = github_user["id"]
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    encrypted_token, iv = encrypt_token(github_token)

    if user:
        user.github_username = github_user.get("login", user.github_username)
        user.email = github_user.get("email")
        user.github_avatar_url = github_user.get("avatar_url")
        user.github_token_encrypted = encrypted_token
        user.github_token_iv = iv
        logger.info("auth.user_updated", github_id=github_id)
    else:
        user = User(
            github_id=github_id,
            github_username=github_user.get("login", ""),
            email=github_user.get("email"),
            github_avatar_url=github_user.get("avatar_url"),
            github_token_encrypted=encrypted_token,
            github_token_iv=iv,
        )
        db.add(user)
        logger.info("auth.user_created", github_id=github_id)

    await db.commit()
    await db.refresh(user)
    return user


async def complete_oauth(
    code: str,
    state: str,
    redis: Redis,
    db: AsyncSession,
) -> tuple[User, str]:
    await validate_oauth_state(redis, state)
    github_token = await exchange_code_for_token(code)
    github_user = await fetch_github_user(github_token)
    user = await upsert_user(db, github_token, github_user)
    jwt = create_access_token(str(user.id))
    return user, jwt
