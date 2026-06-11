# DocMind — Agent Guide

Auto-generate and maintain documentation from any GitHub codebase, powered by Claude.

---

## What is this?

DocMind connects to a GitHub repo, indexes the code with semantic embeddings, and generates documentation (README, API reference, architecture guide, getting-started). Docs stay fresh via GitHub push webhooks that trigger incremental re-indexing.

Stack: FastAPI backend + Next.js frontend + PostgreSQL (metadata) + Qdrant (vectors) + Redis (pub/sub queue).

---

## Stack & Deployment

| Layer | Technology |
|-------|-----------|
| API | FastAPI 0.115.6 + uvicorn |
| Database | PostgreSQL 16 + asyncpg + SQLAlchemy 2.0 |
| Vector store | Qdrant v1.12.1 |
| Queue | Redis 7 pub/sub |
| LLM | Claude claude-sonnet-4-6 (Anthropic) |
| Embeddings | OpenAI text-embedding-3-large (2048 dims) |
| Reranker | Cohere rerank-v3.5 |
| Code parsing | tree-sitter (Python, JS, TS, Go) |
| Tokenisation | tiktoken cl100k_base |
| Auth | GitHub OAuth 2.0 + JWT HS256 (24h expiry) |
| Token storage | AES-256-GCM encrypted in PostgreSQL |
| Frontend | Next.js 16.2.4 + React 19 + Tailwind CSS 4 |
| Migrations | Alembic |
| Logging | structlog (JSON) |
| MCP transport | SSE on port 8001 (mcp[cli] 1.3.0) |

Local deployment: `cd infrastructure && docker-compose up` — starts all 7 services.
API docs: http://localhost:8000/api/docs | Frontend: http://localhost:3000

---

## Related Repos & Cross-Service Contracts

None — this is a standalone project. Intended to be pointed at any external GitHub repo.

---

## What Lives Where (+ landmines)

```
backend/
  api/            FastAPI routers, schemas, middleware, services, utils
  agents/         WriterAgent, ReviewerAgent, QualityCritic, PRCreator
  db/             SQLAlchemy models (models.py), Alembic migrations
  mcp_server/     MCP SSE server (port 8001)
  rag/            RAG pipeline: dense_search, sparse_search, fusion, reranker, generator
  shared/         constants.py, exceptions.py, logging_config.py
  worker/         ingestion pipeline (parsers, chunker, embedder, vector_store)
  tests/          7 test files (pytest + pytest-asyncio)
  pyproject.toml  all Python dependencies + dev extras
frontend/
  src/app/        Next.js pages: landing, dashboard, chat, doc viewer
  src/lib/        api.ts (HTTP client), auth.tsx (auth context)
infrastructure/
  docker-compose.yml   all 7 services
  init-db/             PostgreSQL extension init
```

**Landmines:**
- `backend/db/models.py` — never add a column without a corresponding Alembic migration; the async engine does NOT auto-migrate
- `backend/shared/constants.py` — single source of truth for model names, chunk sizes, rate limits, Redis channel names; change here, test everywhere
- `backend/api/utils/encryption.py` — AES-256-GCM with random IV; never reuse IVs; changing ENCRYPTION_KEY breaks all existing stored tokens
- `backend/api/utils/jwt_utils.py` — changing JWT_ALGORITHM or APP_SECRET_KEY invalidates all active sessions immediately
- `backend/worker/ingestion/embedder.py` — EMBEDDING_DIMENSIONS must match Qdrant collection dimensions; changing dimensions requires re-indexing all projects
- Redis channel names in `shared/constants.py` must match what `worker/worker_main.py` subscribes to — a mismatch silently drops jobs

---

## Key Files

| File | Purpose |
|------|---------|
| `backend/main.py` | FastAPI app entry point, lifespan (DB + Redis init), all routers registered |
| `backend/db/models.py` | All 8 SQLAlchemy models |
| `backend/db/migrations/versions/001_initial_schema.py` | Only migration — creates all 8 tables |
| `backend/shared/constants.py` | All magic numbers, model names, rate limits, Redis channels |
| `backend/api/config.py` | Pydantic Settings — reads all env vars |
| `backend/rag/pipeline.py` | RAG orchestrator: dense + sparse → fusion → rerank → generate |
| `backend/worker/worker_main.py` | Redis pub/sub consumer entry point |
| `backend/mcp_server/server.py` | MCP SSE server with 4 tools |
| `infrastructure/docker-compose.yml` | Full local stack |

---

## Auth / Security Model

- Users authenticate via GitHub OAuth 2.0 (`GET /api/v1/auth/github` → callback → JWT)
- JWT is HS256, signed with `APP_SECRET_KEY`, expires after 24h (`JWT_EXPIRY_HOURS = 24`, `backend/shared/constants.py:39-40`)
- All protected endpoints use `get_current_user` dependency (`backend/api/middleware/auth.py`)
- GitHub OAuth tokens stored encrypted: AES-256-GCM with random IV per token (`backend/api/utils/encryption.py`); stored as `github_token_encrypted` + `github_token_iv` columns (`backend/db/models.py:21-22`)
- GitHub webhook payloads validated with HMAC-SHA256 (`backend/api/utils/hmac_utils.py`)
- Slack webhook payloads validated with HMAC-SHA256 + 5-minute replay window
- Rate limiting: 60 req/min default for all routes (`RATE_LIMIT_DEFAULT`, `backend/shared/constants.py:35`); `RATE_LIMIT_QUERY = 30` is defined but not yet wired per-route

---

## Data Model

8 tables (all defined in `backend/db/models.py`):

```
users                         GitHub OAuth identity, encrypted token
  └── projects                connected repos, ingestion status, config
       ├── documents           source files + generated doc files
       │    └── chunks         token-bounded text windows with embedding IDs
       ├── agent_tasks         async AI task queue (queued/running/completed)
       ├── queries             RAG query log with citations + confidence
       └── integrations        Slack / WhatsApp channel configs

audit_logs                    webhook signature failures, access events
```

All primary keys are UUID. Cascading deletes: project deletion removes all child records and Qdrant vectors.

---

## Env Vars

Names only — never commit values.

| Var | Purpose |
|-----|---------|
| `DATABASE_URL` | PostgreSQL asyncpg connection string |
| `REDIS_URL` | Redis connection URL |
| `QDRANT_HOST` / `QDRANT_PORT` | Qdrant vector store |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | GitHub OAuth app |
| `GITHUB_CALLBACK_URL` | OAuth callback URL |
| `APP_SECRET_KEY` | JWT signing key (32+ chars) |
| `ENCRYPTION_KEY` | AES-256 token encryption key (32+ chars) |
| `OPENAI_API_KEY` | Embeddings |
| `ANTHROPIC_API_KEY` | Claude generation |
| `COHERE_API_KEY` | Reranker |
| `FRONTEND_URL` | CORS allowed origin |
| `SLACK_SIGNING_SECRET` / `SLACK_BOT_TOKEN` | Optional Slack integration |

Copy `.env.example` to `.env` and fill in.

---

## Conventions

- API prefix: `/api/v1` (set in `backend/main.py`)
- All API routes use FastAPI dependency injection for auth (`get_current_user`) and DB (`get_db`)
- Async throughout: `async def` handlers, `AsyncSession`, `AsyncOpenAI`, `redis.asyncio`
- Commit format: `type(scope): description` — types: feat, fix, docs, chore, test, refactor
- Test files in `backend/tests/`; run with `pytest tests/ -v`
- Docker build targets: `api`, `worker`, `agents`, `mcp` (multi-stage Dockerfile in `backend/`)

---

## Skills

This repo uses the MYRA skills pipeline at `.claude/skills/` (git submodule).

To initialise after cloning:
```bash
git submodule update --init
```

Pipeline: `/spec` (intent → issue) → `/execute` (implement) → `/ship` (PR)

---

## How Agents Work Here (Behavioral Contract)

**Verify before asserting**
1. Any claim about code behavior — in docs, PRs, reviews, or commits — cites a `file:line` actually read in this session. *(preventive)*
2. Review findings are claims too — verify them against the code before recording them anywhere. *(preventive)*
3. State assumptions explicitly; verify or surface them — never barrel ahead silently. *(preventive)*

**Simplicity first**
4. Build the minimum that satisfies the acceptance criteria — nothing speculative, no unrequested abstraction or configurability. *(preventive)*
5. Scope growth is proposed (PR note or new issue), never silently built. *(preventive)*

**Surgical changes**
6. Touch only files the spec implies; never stage or commit unrelated working-tree changes. *(preventive)*
7. Match surrounding style; no drive-by refactors or formatting churn. *(preventive)*

**Goal-driven execution**
8. Work enters through a spec with numbered pass/fail acceptance criteria; every criterion maps to a test or command. *(preventive)*
9. Questions front-load to spec time; loop implement → test → self-review until criteria are green before involving a human. *(preventive)*
10. Report outcomes faithfully — `DONE / DONE_WITH_CONCERNS / BLOCKED`; failing or skipped is stated, never rounded up to "done". *(preventive)*

---

## Rules for Agents

1. Never modify `backend/db/models.py` without a corresponding Alembic migration
2. Never change `ENCRYPTION_KEY` or `JWT_ALGORITHM` without a migration plan for existing data
3. Never `git add -A` — stage only spec-implied files
4. Tests must pass before any PR (`pytest tests/ -v`)
5. Secrets never appear in code, commits, or PR bodies — use `.env` and `.env.example`

---

## Risk-class list

Changes to any of these areas **auto-upgrade task size by one** regardless of line count:

- GitHub OAuth flow (`backend/api/routers/auth.py`, `backend/api/services/auth_service.py`)
- Token encryption / decryption (`backend/api/utils/encryption.py`)
- JWT creation / validation (`backend/api/utils/jwt_utils.py`, `backend/api/middleware/auth.py`)
- HMAC webhook signature validation (`backend/api/utils/hmac_utils.py`, `backend/api/routers/webhooks.py`)
- Database schema changes (`backend/db/models.py`, `backend/db/migrations/`)
- Qdrant collection dimensions or embedding model (`backend/shared/constants.py` — `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`)
