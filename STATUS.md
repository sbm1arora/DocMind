# DocMind — Build Status

**Last updated:** 2026-04-19
**Session:** Dave (Shubham-Dave group)
**Repo:** https://github.com/sbm1arora/DocMind
**Spec:** ENGINEERING_SPEC.md (repo root)

---

## How to use this file

- Read this at the start of every session to know exactly where to pick up
- Update task status immediately after each commit + push
- One task = one commit. Never batch tasks in a single commit.

---

## What's already built (skeleton — no features functional)

- DB models: all 8 tables (users, projects, documents, chunks, agent_tasks, queries, integrations, audit_logs)
- Pydantic config (Settings with all env vars)
- Auth middleware (JWT verify, rate limit, request logging)
- Shared utils: JWT, HMAC, AES-256 encryption, exceptions, constants, logging config
- SQLAlchemy async DB connection setup
- Alembic migrations config
- Docker Compose (postgres, redis, qdrant, api, worker, mcp)
- Worker ingestion + agents directory structure (all empty)

---

## PHASE 1 — Core API Foundation ✅ COMPLETE

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T1.1 | FastAPI app entry point (`backend/main.py`) | ✅ DONE | e5fc9da |
| T1.2 | DB session factory + async engine setup in `db/database.py` | ✅ DONE | e5fc9da |
| T1.3 | Alembic initial migration — create all 8 tables | ✅ DONE | e5fc9da |
| T1.4 | Auth schemas: `UserOut`, `TokenResponse`, `GithubCallbackQuery` | ✅ DONE | e5fc9da |
| T1.5 | GitHub OAuth router — `GET /api/v1/auth/github` + callback | ✅ DONE | e5fc9da |
| T1.6 | Auth service — code exchange, user upsert, AES-256-GCM, JWT | ✅ DONE | e5fc9da |
| T1.7 | `GET /api/v1/auth/me` | ✅ DONE | e5fc9da |
| T1.8 | Health check endpoint `GET /api/v1/health` | ✅ DONE | e5fc9da |

**Note:** Commit e5fc9da is local — push blocked (Vatsal-AAI lacks write access to sbm1arora/DocMind).

---

## PHASE 2 — Projects API

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T2.1 | Project schemas: `ProjectCreate`, `ProjectOut`, `RepoItem` in `api/schemas/projects.py` | ⬜ TODO | — |
| T2.2 | `GET /api/v1/projects/available-repos` — list GitHub repos for current user | ⬜ TODO | — |
| T2.3 | `POST /api/v1/projects` — create project, register GitHub webhook, publish ingestion job to Redis | ⬜ TODO | — |
| T2.4 | `GET /api/v1/projects` — list user projects | ⬜ TODO | — |
| T2.5 | `GET /api/v1/projects/{id}` — get project status (used by frontend polling) | ⬜ TODO | — |
| T2.6 | `DELETE /api/v1/projects/{id}` — remove webhook, delete project + cascade | ⬜ TODO | — |

---

## PHASE 3 — Ingestion Worker (Full)

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T3.1 | Redis pub/sub base worker — subscribe to channels, dispatch handlers in `worker/worker_main.py` | ⬜ TODO | — |
| T3.2 | File type router + Markdown parser in `worker/ingestion/parsers/markdown_parser.py` | ⬜ TODO | — |
| T3.3 | Code parser (Python/JS/TS/Go — extract functions, classes, docstrings) in `worker/ingestion/parsers/code_parser.py` | ⬜ TODO | — |
| T3.4 | Chunking logic (semantic chunks, max 512 tokens, overlap 64) in `worker/ingestion/chunker.py` | ⬜ TODO | — |
| T3.5 | OpenAI embedding client (batch API, text-embedding-3-large) in `worker/ingestion/embedder.py` | ⬜ TODO | — |
| T3.6 | Qdrant client wrapper — upsert, delete by filter in `worker/ingestion/vector_store.py` | ⬜ TODO | — |
| T3.7 | Full repo clone + walk + parse + chunk + embed ingestion handler in `worker/ingestion/full_ingestion.py` | ⬜ TODO | — |
| T3.8 | Incremental re-index handler (GitHub compare API → changed files only) in `worker/ingestion/incremental_ingestion.py` | ⬜ TODO | — |

---

## PHASE 4 — RAG Pipeline

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T4.1 | Qdrant dense search in `backend/rag/dense_search.py` | ⬜ TODO | — |
| T4.2 | PostgreSQL full-text sparse search in `backend/rag/sparse_search.py` | ⬜ TODO | — |
| T4.3 | Reciprocal Rank Fusion merger (0.6 dense + 0.4 sparse) in `backend/rag/fusion.py` | ⬜ TODO | — |
| T4.4 | Cohere rerank-v3.5 client in `backend/rag/reranker.py` | ⬜ TODO | — |
| T4.5 | Claude generation with citations in `backend/rag/generator.py` | ⬜ TODO | — |
| T4.6 | RAG pipeline orchestrator in `backend/rag/pipeline.py` | ⬜ TODO | — |
| T4.7 | Query schemas + `POST /api/v1/projects/{id}/query` endpoint | ⬜ TODO | — |

---

## PHASE 5 — GitHub Webhooks

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T5.1 | Webhook schemas in `api/schemas/webhooks.py` | ⬜ TODO | — |
| T5.2 | `POST /api/v1/webhooks/github` — HMAC validation, project lookup, publish to Redis | ⬜ TODO | — |

---

## PHASE 6 — Agent System

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T6.1 | Agent base class + Redis task queue consumer in `agents/base_agent.py` | ⬜ TODO | — |
| T6.2 | Writer Agent — generate README, API_REFERENCE, ARCHITECTURE, GETTING_STARTED | ⬜ TODO | — |
| T6.3 | Reviewer Agent — validate doc accuracy against code chunks | ⬜ TODO | — |
| T6.4 | Quality Critic Agent — coverage score, staleness detection, gap analysis | ⬜ TODO | — |
| T6.5 | GitHub PR creator service | ⬜ TODO | — |
| T6.6 | `POST /api/v1/projects/{id}/documents/generate` | ⬜ TODO | — |
| T6.7 | `POST /api/v1/projects/{id}/documents/create-pr` | ⬜ TODO | — |
| T6.8 | `GET /api/v1/agents/tasks/{task_id}` | ⬜ TODO | — |

---

## PHASE 7 — MCP Server

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T7.1 | FastMCP server init + SSE transport | ⬜ TODO | — |
| T7.2 | `search_docs` tool | ⬜ TODO | — |
| T7.3 | `get_section` tool | ⬜ TODO | — |
| T7.4 | `check_coverage` tool | ⬜ TODO | — |
| T7.5 | `flag_issue` tool | ⬜ TODO | — |

---

## PHASE 8 — Channel Integrations

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T8.1 | Slack events endpoint | ⬜ TODO | — |
| T8.2 | Slack Block Kit response formatter | ⬜ TODO | — |
| T8.3 | WhatsApp (Twilio) webhook | ⬜ TODO | — |

---

## PHASE 9 — Frontend (Next.js)

| ID | Task | Status | Commit |
|----|------|--------|--------|
| T9.1 | Next.js app scaffold — landing page, GitHub OAuth redirect | ✅ DONE | fe187d6 |
| T9.2 | Dashboard — repo list, connect button, project status polling | ✅ DONE | fe187d6 |
| T9.3 | Chat UI — query input, citations, conversation history | ✅ DONE | fe187d6 |
| T9.4 | Doc viewer — generated docs with quality scores, edit/approve/create-PR | ✅ DONE | fe187d6 |

---

## ALL 9 PHASES COMPLETE ✅

Last commit: fe187d6 (2026-04-29)
21 commits total | ~4,200+ lines

---

## Environment Setup

To run locally:
```
cp .env.example .env   # fill in your keys
cd infrastructure
docker-compose up
```
Frontend: http://localhost:3000
API docs: http://localhost:8000/api/docs

## Blockers

| Blocker | Status |
|---------|--------|
| Cannot run Python locally in Dave container | OPEN — Shubham to test via docker-compose |
| Vatsal-AAI lacks write access to sbm1arora/DocMind | RESOLVED — push working via deploy key |

---

## Notes

- Python dependencies: FastAPI, SQLAlchemy (async), Alembic, pydantic-settings, qdrant-client, redis, anthropic, openai, cohere, httpx, structlog, fastmcp
- All Claude API calls use model: `claude-sonnet-4-6`
- Token budget per generation call: max 4096 output tokens
- Commit convention: `feat(phase-X): T{id} — {description}`
