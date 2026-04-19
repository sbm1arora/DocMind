"""
Incremental re-index handler — triggered by GitHub push webhooks.

Flow:
1. Fetch diff from GitHub compare API (before_sha...after_sha)
2. For each changed file: delete old vectors + chunks, re-parse and re-embed
3. Mark generated docs that referenced changed files as "stale"
4. Publish "ingestion:incremental_complete" event
"""

import hashlib
import json
import structlog
import httpx
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import select, delete as sa_delete, update
from sqlalchemy.text import text

from api.utils.encryption import decrypt_token
from db.models import Project, Document, Chunk as ChunkModel, User
from db.database import AsyncSessionLocal
from shared.constants import (
    ALL_CODE_EXTENSIONS,
    ALL_DOC_EXTENSIONS,
    REDIS_CHANNEL_INGESTION,
    MAX_FILE_SIZE_KB,
)
from worker.ingestion.parsers.markdown_parser import parse_doc_file
from worker.ingestion.parsers.code_parser import parse_code_file
from worker.ingestion.chunker import chunk_sections, chunk_symbols, Chunk
from worker.ingestion.embedder import embed_texts
from worker.ingestion.vector_store import delete_by_document, upsert_chunks
from worker.ingestion.full_ingestion import _detect_language, _is_code_file, _is_doc_file, _sha256

logger = structlog.get_logger()

GITHUB_API = "https://api.github.com"
MAX_FILE_BYTES = MAX_FILE_SIZE_KB * 1024


async def _fetch_diff(token: str, repo_full_name: str, before_sha: str, after_sha: str) -> list[dict]:
    """Return list of changed file dicts from GitHub compare API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo_full_name}/compare/{before_sha}...{after_sha}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub compare failed: {resp.status_code}")
    data = resp.json()
    return data.get("files", [])


async def _fetch_file_content(token: str, repo_full_name: str, file_path: str, ref: str) -> str | None:
    """Fetch raw file content from GitHub at a specific ref."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GITHUB_API}/repos/{repo_full_name}/contents/{file_path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"},
            params={"ref": ref},
        )
    if resp.status_code == 404:
        return None  # file deleted
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub contents fetch failed: {resp.status_code} for {file_path}")
    return resp.text


async def handle_incremental_ingestion(
    redis: Redis,
    project_id: str,
    before_sha: str,
    after_sha: str,
) -> None:
    logger.info("ingestion.incremental.start", project_id=project_id,
                before=before_sha[:8], after=after_sha[:8])

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            logger.error("ingestion.project_not_found", project_id=project_id)
            return

        user_result = await db.execute(select(User).where(User.id == project.user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return

        github_token = decrypt_token(user.github_token_encrypted, user.github_token_iv)

        try:
            changed_files = await _fetch_diff(github_token, project.repo_full_name, before_sha, after_sha)

            if len(changed_files) > 500:
                # Too large — trigger full re-index instead
                logger.info("ingestion.incremental.too_large_triggering_full", count=len(changed_files))
                from worker.ingestion.full_ingestion import handle_full_ingestion
                await handle_full_ingestion(redis, project_id)
                return

            updated_paths: list[str] = []

            for file_info in changed_files:
                file_path = file_info["filename"]
                status = file_info["status"]  # added, modified, removed, renamed

                language = _detect_language(file_path)
                if not language:
                    continue

                # Always delete old vectors + chunk records for this file
                await delete_by_document(project_id, file_path)
                await db.execute(
                    sa_delete(ChunkModel).where(
                        ChunkModel.project_id == project_id,
                    ).where(
                        ChunkModel.document_id.in_(
                            select(Document.id).where(
                                Document.project_id == project_id,
                                Document.file_path == file_path,
                            )
                        )
                    )
                )
                await db.execute(
                    sa_delete(Document).where(
                        Document.project_id == project_id,
                        Document.file_path == file_path,
                    )
                )
                await db.commit()

                if status == "removed":
                    continue

                content = await _fetch_file_content(
                    github_token, project.repo_full_name, file_path, after_sha
                )
                if not content or not content.strip():
                    continue

                if len(content.encode()) > MAX_FILE_BYTES:
                    logger.info("ingestion.file_skipped_large", path=file_path)
                    continue

                content_hash = _sha256(content)
                doc = Document(
                    project_id=project_id,
                    file_path=file_path,
                    doc_type="code" if _is_code_file(file_path) else "doc",
                    language=language,
                    content_hash=content_hash,
                    last_code_commit=after_sha,
                    status="current",
                )
                db.add(doc)
                await db.flush()

                # Parse + chunk
                chunks: list[Chunk] = []
                if _is_code_file(file_path) and language:
                    symbols = parse_code_file(content, file_path, language)
                    chunks = chunk_symbols(symbols, file_path)
                elif _is_doc_file(file_path):
                    sections = parse_doc_file(content, file_path)
                    chunks = chunk_sections(sections)

                if chunks:
                    texts = [c.content for c in chunks]
                    embeddings = await embed_texts(texts)

                    chunk_ids = []
                    payloads = []
                    chunk_records = []
                    for chunk, embedding in zip(chunks, embeddings):
                        chunk_id = str(uuid4())
                        chunk_ids.append(chunk_id)
                        payloads.append({
                            "project_id": project_id,
                            "document_id": str(doc.id),
                            "chunk_id": chunk_id,
                            "chunk_type": chunk.chunk_type,
                            "symbol_name": chunk.symbol_name,
                            "file_path": file_path,
                            "content": chunk.content[:500],
                        })
                        chunk_records.append(ChunkModel(
                            id=chunk_id,
                            document_id=str(doc.id),
                            project_id=project_id,
                            content=chunk.content,
                            chunk_type=chunk.chunk_type,
                            chunk_index=chunk.chunk_index,
                            start_line=chunk.start_line,
                            end_line=chunk.end_line,
                            token_count=chunk.token_count,
                            symbol_name=chunk.symbol_name,
                            is_public=chunk.is_public,
                            parent_context=chunk.parent_context,
                            embedding_id=chunk_id,
                            metadata=chunk.metadata,
                        ))

                    await upsert_chunks(chunk_ids, embeddings, payloads)
                    db.add_all(chunk_records)
                    await db.commit()

                updated_paths.append(file_path)
                logger.info("ingestion.file_reindexed", path=file_path, chunks=len(chunks))

            # Mark generated docs that reference changed files as stale
            if updated_paths:
                await db.execute(
                    update(Document)
                    .where(
                        Document.project_id == project_id,
                        Document.doc_type == "generated",
                        Document.status == "current",
                    )
                    .values(status="stale")
                )
                await db.commit()

            # Update project commit SHA
            project.last_commit_sha = after_sha
            await db.commit()

            await redis.publish(
                REDIS_CHANNEL_INGESTION,
                json.dumps({
                    "event": "ingestion:incremental_complete",
                    "project_id": project_id,
                    "updated_files": updated_paths,
                    "after_sha": after_sha,
                }),
            )
            logger.info("ingestion.incremental.complete", project_id=project_id,
                        updated=len(updated_paths))

        except Exception as e:
            logger.error("ingestion.incremental.failed", project_id=project_id,
                         error=str(e), exc_info=True)
