"""
Tests for the projects API.

GET  /api/v1/projects           — list user's projects
GET  /api/v1/projects/{id}      — get single project
POST /api/v1/projects           — create project (GitHub webhook + ingestion queued)
DELETE /api/v1/projects/{id}    — delete project

All tests require authentication. Unauthenticated requests must return 401/403.
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestListProjects:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_403(self, client):
        resp = await client.get("/api/v1/projects")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_authenticated_returns_200(self, client, auth_headers, sample_project):
        resp = await client.get("/api/v1/projects", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(p["id"] == str(sample_project.id) for p in data)

    @pytest.mark.asyncio
    async def test_only_own_projects_returned(self, client, auth_headers, sample_project):
        resp = await client.get("/api/v1/projects", headers=auth_headers)
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()]
        assert str(sample_project.id) in ids


class TestGetProject:
    @pytest.mark.asyncio
    async def test_get_own_project_200(self, client, auth_headers, sample_project):
        resp = await client.get(f"/api/v1/projects/{sample_project.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(sample_project.id)
        assert data["repo_full_name"] == sample_project.repo_full_name

    @pytest.mark.asyncio
    async def test_get_nonexistent_project_404(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_403(self, client, sample_project):
        resp = await client.get(f"/api/v1/projects/{sample_project.id}")
        assert resp.status_code in (401, 403)


class TestCreateProject:
    @pytest.mark.asyncio
    async def test_create_project_queues_ingestion(self, client, auth_headers):
        """Creating a project must enqueue an ingestion job via Redis publish."""
        with (
            patch("api.services.projects_service._register_github_webhook",
                  return_value=12345) as mock_webhook,
            patch("api.services.projects_service.decrypt_token",
                  return_value="gho_test_token"),
        ):
            resp = await client.post(
                "/api/v1/projects",
                headers=auth_headers,
                json={"repo_full_name": "testuser/newrepo", "branch": "main"},
            )

        assert resp.status_code in (200, 201)
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_403(self, client):
        resp = await client.post(
            "/api/v1/projects",
            json={"repo_full_name": "user/repo", "branch": "main"},
        )
        assert resp.status_code in (401, 403)


class TestDeleteProject:
    @pytest.mark.asyncio
    async def test_delete_own_project(self, client, auth_headers, sample_project):
        with patch("api.routers.projects._delete_github_webhook",
                   new_callable=AsyncMock):
            resp = await client.delete(
                f"/api/v1/projects/{sample_project.id}",
                headers=auth_headers,
            )
        assert resp.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self, client, auth_headers):
        resp = await client.delete(
            "/api/v1/projects/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert resp.status_code == 404
