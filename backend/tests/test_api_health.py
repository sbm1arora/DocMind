"""
Tests for the health endpoint.

GET /api/v1/health — must return 200 with db/redis status.
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("GITHUB_CLIENT_ID", "test")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test")
os.environ.setdefault("GITHUB_CALLBACK_URL", "http://localhost/cb")
os.environ.setdefault("APP_SECRET_KEY", "test_secret_key_32bytes_minimum!!")
os.environ.setdefault("ENCRYPTION_KEY", "test_encryption_key_32bytes_min!!")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("COHERE_API_KEY", "test")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

from main import app


@pytest.mark.asyncio
async def test_health_endpoint_ok():
    """Health endpoint returns 200 when DB and Redis are reachable."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.publish = AsyncMock(return_value=1)
    mock_redis.aclose = AsyncMock()

    with patch("main.Redis") as mock_redis_cls:
        mock_redis_cls.from_url.return_value = mock_redis

        async with app.router.lifespan_context(app):
            app.state.redis = mock_redis
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                with patch("api.routers.health.text") as mock_text:
                    # Simulate DB executing OK
                    mock_text.return_value = "SELECT 1"
                    resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
