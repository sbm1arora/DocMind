"""
Tests for the agent task endpoints.

POST /api/v1/projects/{id}/documents/generate  — queue writer agent
POST /api/v1/projects/{id}/documents/create-pr — queue PR creator
GET  /api/v1/agents/tasks/{task_id}            — poll task status
"""

import pytest
from unittest.mock import AsyncMock, patch
from db.models import AgentTask


class TestGenerateDocuments:
    @pytest.mark.asyncio
    async def test_requires_indexed_project(self, client, auth_headers, db_session, sample_project):
        """Non-indexed project must return 422."""
        sample_project.status = "pending"
        await db_session.commit()

        resp = await client.post(
            f"/api/v1/projects/{sample_project.id}/documents/generate",
            headers=auth_headers,
            json={"doc_types": ["readme"]},
        )
        assert resp.status_code == 422

        # Restore for other tests
        sample_project.status = "indexed"
        await db_session.commit()

    @pytest.mark.asyncio
    async def test_returns_202_with_task_id(self, client, auth_headers, sample_project):
        """Indexed project must return 202 with a task_id."""
        resp = await client.post(
            f"/api/v1/projects/{sample_project.id}/documents/generate",
            headers=auth_headers,
            json={"doc_types": ["readme", "api_reference"]},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_403(self, client, sample_project):
        resp = await client.post(
            f"/api/v1/projects/{sample_project.id}/documents/generate",
            json={"doc_types": ["readme"]},
        )
        assert resp.status_code in (401, 403)


class TestGetTaskStatus:
    @pytest.mark.asyncio
    async def test_get_own_task(self, client, auth_headers, db_session, sample_project):
        """Polling a task belonging to the user's project must return 200."""
        task = AgentTask(
            project_id=sample_project.id,
            task_type="generate_docs",
            status="completed",
            input={"doc_types": ["readme"]},
            output={"documents": [{"doc_type": "readme", "document_id": "abc"}]},
        )
        db_session.add(task)
        await db_session.commit()
        await db_session.refresh(task)

        resp = await client.get(
            f"/api/v1/agents/tasks/{task.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(task.id)
        assert data["status"] == "completed"
        assert data["task_type"] == "generate_docs"

    @pytest.mark.asyncio
    async def test_nonexistent_task_returns_404(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/agents/tasks/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_403(self, client, sample_project):
        resp = await client.get("/api/v1/agents/tasks/some-id")
        assert resp.status_code in (401, 403)
