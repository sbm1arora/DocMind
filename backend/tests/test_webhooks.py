"""
Tests for the GitHub webhook endpoint.

POST /api/v1/webhooks/github

Covers:
  - Valid push event with correct HMAC → 200 accepted
  - Wrong HMAC → 401
  - Non-push event → 200 ignored
  - Project not found → 200 ignored
  - No-op push (branch create) → 200 ignored
"""

import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Signature helpers ─────────────────────────────────────────────────────────

def _sign(payload: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


# ── Push payload factory ──────────────────────────────────────────────────────

def _push_payload(repo: str = "owner/repo", before: str = "a" * 40, after: str = "b" * 40) -> dict:
    return {
        "repository": {"full_name": repo},
        "before": before,
        "after": after,
        "ref": "refs/heads/main",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestGitHubWebhook:
    @pytest.mark.asyncio
    async def test_non_push_event_ignored(self, client):
        """Non-push events (e.g. ping) must be acknowledged but ignored."""
        payload = json.dumps({"zen": "Keep it logically awesome."}).encode()
        resp = await client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "ping",
                "X-Hub-Signature-256": _sign(payload, "any"),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_project_not_found_ignored(self, client):
        """Push for an unknown repo must return 200 ignored."""
        payload = json.dumps(_push_payload(repo="unknown/repo")).encode()
        resp = await client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _sign(payload, "secret"),
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_branch_create_noop_ignored(self, client, sample_project):
        """A push with before=0*40 (branch creation) must be ignored."""
        payload = json.dumps(
            _push_payload(
                repo=sample_project.repo_full_name,
                before="0" * 40,
                after="b" * 40,
            )
        ).encode()
        sig = _sign(payload, sample_project.webhook_secret)
        resp = await client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_401(self, client, sample_project):
        """A push with a bad HMAC must return 401."""
        payload = json.dumps(_push_payload(repo=sample_project.repo_full_name)).encode()
        resp = await client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": "sha256=badhash",
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_push_accepted(self, client, sample_project):
        """A valid push event with correct HMAC must return 200 accepted."""
        payload_dict = _push_payload(repo=sample_project.repo_full_name)
        payload = json.dumps(payload_dict).encode()
        sig = _sign(payload, sample_project.webhook_secret)

        resp = await client.post(
            "/api/v1/webhooks/github",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        assert resp.json()["project_id"] == str(sample_project.id)
