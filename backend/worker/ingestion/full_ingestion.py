"""
Full repository ingestion handler.

Flow:
1. Clone repo (shallow, depth=1) to /tmp/repos/{project_id}
2. Walk file tree, filter by supported extensions
3. For each file: parse → chunk → embed → upsert to Qdrant + Postgres
4. Update project status to "indexed"
5. Publish "ingestion:complete" event to Redis
"""

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import structlog
from pathlib import Path
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from api.config import settings
from api.utils.encryption import decrypt_token
from db.models import Project, Document, Chunk as ChunkModel, User
from db.database import AsyncSessionLocal
from shared.constants import (
    ALL_CODE_EXTENSIONS,
    ALL_DOC_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    MAX_FILE_SIZE_KB,
    REDIS_CHANNEL_INGESTION,
)
from worker.ingestion.parsers.markdown_parser import parse_doc_file
from worker.ingestion.parsers.code_parser import parse_code_file
from worker.ingestion.chunker import chunk_sections, chunk_symbols, Chunk
from worker.ingestion.embedder import embed_texts
from worker.ingestion.vector_store import upsert_chunks, delete_by_project

from sqlalchemy import select, delete as sa_delete

logger = structlog.get_logger()

CLONE_BASE = "/tmp/repos"
MAX_FILE_BYTES = MAX_FILE_SIZE_KB * 1024


def _detect_language(file_path: str) -> str | None:
    ext = Path(file_path).suffix.lower()
    for lang, exts in SUPPORTED_EXTENSIONS.items():
        if ext in exts:
            return lang
    return None


def _is_code_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in ALL_CODE_EXTENSIONS


def _is_doc_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in ALL_DOC_EXTENSIONS


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def _clone_repo(repo_full_name: str, github_token: str, dest: str) -> None:
    url = f"https://x-access-token:{github_token}@github.com/{repo_full_name}.git"
    proc = await asyncio.create_subprocess_exec(
        "git", "clone", "--depth=1", url, dest,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed: {stderr.decode()}")


async def _process_file(
    db: AsyncSession,
    project_id: str,
    file_path: str,
    abs_path: str,
    rel_path: str,
) -> list[tuple[Chunk, str]]:
    """Parse and chunk one file. Returns list of (Chunk, doc_id) tuples."""
    try:
        size = os.path.getsize(abs_path)
        if size > MAX_FILE_BYTES:
            logger.info("ingestion.file_skipped_large", path=rel_path, size_kb=size // 1024)
            return []

        with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if not content.strip():
            return []

        language = _detect_language(rel_path)
        content_hash = _sha256(content)

        # Upsert document record
        existing = await db.execute(
            select(Document).where(
                Document.project_id == project_id,
                Document.file_path == rel_path,
            )
        )
        doc = existing.scalar_one_or_none()
        if doc and doc.content_hash == content_hash:
            logger.debug("ingestion.file_unchanged", path=rel_path)
            return []

        if doc:
            doc.content_hash = content_hash
            doc.status = "current"
        else:
            doc = Document(
                project_id=project_id,
                file_path=rel_path,
                doc_type="code" if _is_code_file(rel_path) else "doc",
                language=language,
                content_hash=content_hash,
                status="current",
            )
            db.add(doc)
            await db.flush()

        # Parse
        chunks: list[Chunk] = []
        if _is_code_file(rel_path) and language:
            symbols = parse_code_file(content, rel_path, language)
            chunks = chunk_symbols(symbols, rel_path)
        elif _is_doc_file(rel_path):
            sections = parse_doc_file(content, rel_path)
            chunks = chunk_sections(sections)

        return [(c, str(doc.id)) for c in chunks]

    except Exception as e:
        logger.error("ingestion.file_error", path=rel_path, error=str(e))
        return []


async def handle_full_ingestion(redis: Redis, project_id: str) -> None:
    logger.info("ingestion.full.start", project_id=project_id)
    clone_dir = f"{CLONE_BASE}/{project_id}"

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
            # Clean previous clone if exists
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir)

            await _clone_repo(project.repo_full_name, github_token, clone_dir)
            logger.info("ingestion.cloned", project_id=project_id, path=clone_dir)

            # Clear existing vectors for this project
            await delete_by_project(project_id)

            # Delete existing chunk + document records
            await db.execute(
                sa_delete(ChunkModel).where(ChunkModel.project_id == project_id)
            )
            await db.execute(
                sa_delete(Document).where(Document.project_id == project_id)
            )
            await db.commit()

            # Walk files
            all_chunk_tuples: list[tuple[Chunk, str]] = []
            file_count = 0

            for root, dirs, files in os.walk(clone_dir):
                # Skip hidden + vendor dirs
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (
                    "node_modules", "vendor", "__pycache__", ".git", "dist", "build",
                )]
                for fname in files:
                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, clone_dir)
                    language = _detect_language(rel_path)
                    if not language:
                        continue
                    chunk_tuples = await _process_file(db, project_id, abs_path, abs_path, rel_path)
                    all_chunk_tuples.extend(chunk_tuples)
                    file_count += 1

            await db.commit()

            # Embed + upsert in batches
            total_chunks = len(all_chunk_tuples)
            if total_chunks > 0:
                texts = [c.content for c, _ in all_chunk_tuples]
                embeddings = await embed_texts(texts)

                chunk_ids = []
                payloads = []
                chunk_records = []

                for (chunk, doc_id), embedding in zip(all_chunk_tuples, embeddings):
                    chunk_id = str(uuid4())
                    chunk_ids.append(chunk_id)
                    payloads.append({
                        "project_id": project_id,
                        "document_id": doc_id,
                        "chunk_id": chunk_id,
                        "chunk_type": chunk.chunk_type,
                        "symbol_name": chunk.symbol_name,
                        "content": chunk.content[:500],  # payload preview
                    })
                    chunk_records.append(ChunkModel(
                        id=chunk_id,
                        document_id=doc_id,
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

            # Update project status
            project.status = "indexed"
            project.file_count = file_count
            project.chunk_count = total_chunks
            await db.commit()

            await redis.publish(
                REDIS_CHANNEL_INGESTION,
                json.dumps({
                    "event": "ingestion:complete",
                    "project_id": project_id,
                    "file_count": file_count,
                    "chunk_count": total_chunks,
                }),
            )
            logger.info("ingestion.full.complete", project_id=project_id,
                        files=file_count, chunks=total_chunks)

        except Exception as e:
            logger.error("ingestion.full.failed", project_id=project_id, error=str(e), exc_info=True)
            project.status = "error"
            await db.commit()

        finally:
            if os.path.exists(clone_dir):
                shutil.rmtree(clone_dir, ignore_errors=True)
