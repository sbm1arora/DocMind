"""
GitHub PR creator — creates a branch, commits generated docs, opens a PR.
"""

import base64
import structlog
import httpx
from datetime import datetime

from api.config import settings
from api.utils.encryption import decrypt_token

logger = structlog.get_logger()

GITHUB_API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


async def create_docs_pr(
    github_token: str,
    repo_full_name: str,
    base_branch: str,
    documents: list[dict],  # [{"file_path": str, "content": str, "title": str}]
    pr_title: str,
    pr_body: str,
) -> str:
    """
    Create a GitHub PR with the given documents.

    Returns the PR URL.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    branch_name = f"docs/docmind-{timestamp}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get default branch SHA
        ref_resp = await client.get(
            f"{GITHUB_API}/repos/{repo_full_name}/git/ref/heads/{base_branch}",
            headers=_headers(github_token),
        )
        ref_resp.raise_for_status()
        base_sha = ref_resp.json()["object"]["sha"]

        # Create new branch
        await client.post(
            f"{GITHUB_API}/repos/{repo_full_name}/git/refs",
            headers=_headers(github_token),
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )

        # Commit each document file
        for doc in documents:
            file_path = doc["file_path"]
            content_b64 = base64.b64encode(doc["content"].encode()).decode()

            # Check if file exists (to get its SHA for update)
            existing = await client.get(
                f"{GITHUB_API}/repos/{repo_full_name}/contents/{file_path}",
                headers=_headers(github_token),
                params={"ref": branch_name},
            )
            payload: dict = {
                "message": f"docs: Add/update {file_path} [DocMind]",
                "content": content_b64,
                "branch": branch_name,
            }
            if existing.status_code == 200:
                payload["sha"] = existing.json()["sha"]

            await client.put(
                f"{GITHUB_API}/repos/{repo_full_name}/contents/{file_path}",
                headers=_headers(github_token),
                json=payload,
            )

        # Open PR
        pr_resp = await client.post(
            f"{GITHUB_API}/repos/{repo_full_name}/pulls",
            headers=_headers(github_token),
            json={
                "title": pr_title,
                "body": pr_body,
                "head": branch_name,
                "base": base_branch,
            },
        )
        pr_resp.raise_for_status()
        pr_url = pr_resp.json()["html_url"]
        logger.info("pr_creator.pr_created", url=pr_url, repo=repo_full_name)
        return pr_url
