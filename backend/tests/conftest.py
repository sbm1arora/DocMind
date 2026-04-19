"""
pytest fixtures shared across all test modules.

Uses an in-memory SQLite database so tests run without a Postgres instance.
External services (Redis, Qdrant, OpenAI, Anthropic, Cohere) are mocked.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# ── Environment overrides BEFORE any app imports ──────────────────────────────
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("GITHUB_CLIENT_ID", "test_client_id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("GITHUB_CALLBACK_URL", "http://localhost:8000/api/v1/auth/github/callback")
os.environ.setdefault("APP_SECRET_KEY", "test_secret_key_32bytes_minimum!!")
os.environ.setdefault("ENCRYPTION_KEY", "test_encryption_key_32bytes_min!!")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("COHERE_API_KEY", "test-cohere-key")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from main import app
from db.database import Base, AsyncSessionLocal
from db.models import User, Project, Document, Chunk, AgentTask
from api.utils.jwt_utils import create_access_token
from api.utils.encryption import encrypt_token


@pytest_asyncio.fixture(scope="session")
async def test_app():
    """Yield the FastAPI app with mocked Redis."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.publish = AsyncMock(return_value=1)
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)

    with patch("main.Redis") as mock_redis_cls:
        mock_redis_cls.from_url.return_value = mock_redis
        mock_redis.aclose = AsyncMock()
        async with app.router.lifespan_context(app):
            app.state.redis = mock_redis
            yield app


@pytest_asyncio.fixture
async def client(test_app):
    """Async HTTP client wired to the test app."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """Async DB session for direct DB manipulation in tests."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
def sample_user_data():
    """Raw GitHub user API response fixture."""
    return {
        "id": 12345678,
        "login": "testuser",
        "email": "test@example.com",
        "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
        "name": "Test User",
    }


@pytest_asyncio.fixture
async def sample_user(db_session):
    """A persisted User in the test database."""
    ciphertext, iv = encrypt_token("gho_test_github_token")
    user = User(
        github_id=12345678,
        github_username="testuser",
        email="test@example.com",
        github_avatar_url="https://example.com/avatar.png",
        github_token_encrypted=ciphertext,
        github_token_iv=iv,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(sample_user):
    """Authorization headers with a valid JWT for sample_user."""
    token = create_access_token(str(sample_user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_project(db_session, sample_user):
    """A persisted indexed Project owned by sample_user."""
    project = Project(
        user_id=sample_user.id,
        repo_full_name="testuser/testrepo",
        repo_name="testrepo",
        repo_owner="testuser",
        default_branch="main",
        webhook_id=99999,
        webhook_secret="test_webhook_secret",
        status="indexed",
        file_count=10,
        chunk_count=50,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project
