# DocMind

**Auto-generate and maintain documentation from your codebase — powered by Claude.**

DocMind connects to your GitHub repository, indexes the code with semantic embeddings, and generates high-quality documentation (README, API reference, architecture guide, getting started). It keeps docs fresh automatically via GitHub webhook push events.

---

## Features

- **Automatic indexing** — shallow-clone your repo, parse every Python / JS / TS / Go file with tree-sitter, chunk with tiktoken, embed with OpenAI `text-embedding-3-large`
- **RAG query endpoint** — dense (Qdrant) + sparse (PostgreSQL FTS) retrieval, RRF fusion, Cohere rerank, Claude generation
- **Doc generation** — README, API reference, architecture, and getting-started guides written by Claude and committed via GitHub PR
- **Live updates** — GitHub push webhook triggers incremental re-index of changed files only
- **Slack & WhatsApp** — ask questions about your codebase from Slack mentions or WhatsApp (Twilio)
- **MCP server** — expose DocMind as an MCP tool for Claude Code and other MCP clients
- **Quality scoring** — automated reviewer agent scores generated docs on accuracy, completeness, clarity, examples, and currency

---

## Architecture

```
┌─────────────┐    OAuth     ┌──────────────┐    pub/sub    ┌──────────────┐
│  Frontend   │ ──────────► │  FastAPI API  │ ────────────► │   Worker     │
│  (React)    │             │  (port 8000)  │               │  (ingestion) │
└─────────────┘             └──────┬───────┘               └──────┬───────┘
                                   │                              │
                            ┌──────▼───────┐    embed     ┌──────▼───────┐
                            │  PostgreSQL  │              │    Qdrant    │
                            │  (metadata,  │              │  (vectors)   │
                            │   chunks FTS)│              └──────────────┘
                            └──────────────┘

┌─────────────┐    SSE      ┌──────────────┐
│ Claude Code │ ──────────► │  MCP Server  │
│  / MCP      │             │  (port 8001) │
└─────────────┘             └──────────────┘
```

**Component responsibilities:**

| Component | Responsibility |
|-----------|---------------|
| `api/` | FastAPI routers, auth (GitHub OAuth + JWT), projects CRUD, RAG query endpoint, webhook handler, agent task queue |
| `worker/` | Redis pub/sub consumer; runs full and incremental ingestion pipelines |
| `rag/` | Dense search (Qdrant) + sparse search (PG FTS) → RRF fusion → Cohere rerank → Claude generation |
| `agents/` | WriterAgent (doc generation), ReviewerAgent (quality scoring), QualityCritic (coverage), PRCreator (GitHub PR) |
| `mcp_server/` | MCP SSE server exposing `search_docs`, `get_section`, `check_coverage`, `flag_issue` tools |
| `db/` | SQLAlchemy models, Alembic migrations |
| `shared/` | Constants, exceptions, logging config |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI 0.115 + uvicorn |
| Database | PostgreSQL 16 (asyncpg + SQLAlchemy 2.0) |
| Vector store | Qdrant |
| Cache / queue | Redis (pub/sub) |
| LLM | Anthropic Claude claude-sonnet-4-6 |
| Embeddings | OpenAI text-embedding-3-large (2048 dims) |
| Reranker | Cohere rerank-v3.5 |
| Code parsing | tree-sitter (Python, JS, TS, Go) |
| Tokenisation | tiktoken (cl100k_base) |
| Auth | GitHub OAuth 2.0 + JWT (HS256, 24h) |
| Token storage | AES-256-GCM (encrypted in PG) |
| Migrations | Alembic |
| Logging | structlog (JSON) |
| MCP transport | SSE (mcp[cli] 1.3.0) |

---

## API Reference

All routes are prefixed with `/api/v1`.

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/github` | Initiate GitHub OAuth flow (redirects to GitHub) |
| `GET` | `/auth/github/callback` | OAuth callback — exchanges code for JWT |
| `GET` | `/auth/me` | Return authenticated user profile |

### Projects

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects` | List user's connected repositories |
| `POST` | `/projects` | Connect a GitHub repo (registers webhook, queues ingestion) |
| `GET` | `/projects/{id}` | Get project details + status |
| `DELETE` | `/projects/{id}` | Delete project (removes webhook, Qdrant vectors, all data) |
| `GET` | `/projects/{id}/repos` | List available GitHub repos for the authenticated user |

### Queries

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/projects/{id}/query` | Ask a natural language question about the indexed codebase |

### Agents

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/projects/{id}/documents/generate` | Queue doc generation (writer agent) |
| `POST` | `/projects/{id}/documents/create-pr` | Queue GitHub PR creation for generated docs |
| `GET` | `/agents/tasks/{task_id}` | Poll task status + output |

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhooks/github` | Receive GitHub push events (HMAC validated) |

### Integrations

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/integrations/slack/events` | Slack app_mention event handler |
| `POST` | `/integrations/whatsapp/webhook` | Twilio WhatsApp inbound handler |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns DB + Redis connectivity status |

---

## Query Response Schema

```json
{
  "answer": "Claude's grounded answer",
  "citations": ["file_path:line_range"],
  "confidence": 0.85,
  "follow_ups": ["follow-up question 1", "follow-up question 2"],
  "chunks_used": ["chunk-uuid-1", "chunk-uuid-2"],
  "latency_ms": 1234
}
```

---

## Setup

### Prerequisites

- Python 3.12+
- PostgreSQL 16
- Redis 7+
- Qdrant (latest)
- GitHub OAuth App
- OpenAI API key
- Anthropic API key
- Cohere API key

### Environment variables

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/docmind
REDIS_URL=redis://localhost:6379/0
QDRANT_HOST=localhost
QDRANT_PORT=6333

GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
GITHUB_CALLBACK_URL=http://localhost:8000/api/v1/auth/github/callback

APP_SECRET_KEY=your-32-char-minimum-secret-key
ENCRYPTION_KEY=your-32-char-minimum-encryption-key

OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
COHERE_API_KEY=...

FRONTEND_URL=http://localhost:3000

# Optional integrations
SLACK_SIGNING_SECRET=...
SLACK_BOT_TOKEN=xoxb-...
```

### Install and run

```bash
cd backend
pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# API server
uvicorn main:app --reload --port 8000

# Worker (separate terminal)
python -m worker.worker_main

# MCP server (optional)
python -m mcp_server.server
```

---

## Running Tests

```bash
cd backend
pytest tests/ -v --cov=. --cov-report=term-missing
```

| Test file | Coverage area |
|-----------|--------------|
| `tests/test_utils.py` | encryption, JWT, HMAC, chunker, parsers |
| `tests/test_ingestion.py` | language detection, embedder (mocked), sha256 |
| `tests/test_rag.py` | RRF fusion, generator (mocked), full pipeline (mocked) |
| `tests/test_api_projects.py` | projects CRUD endpoints |
| `tests/test_api_agents.py` | agent task endpoints |
| `tests/test_api_health.py` | health endpoint |
| `tests/test_webhooks.py` | GitHub webhook HMAC + dispatch |

---

## Data Model

```
users
  └── projects (one user → many projects)
       ├── documents (source files + generated docs)
       │    └── chunks (text windows with embeddings)
       ├── agent_tasks (queued / running / completed AI tasks)
       ├── queries (RAG query log)
       └── integrations (Slack, WhatsApp configs)

audit_logs (webhook signature failures, access events)
```

---

## Security

- GitHub OAuth tokens encrypted at rest with AES-256-GCM (random IV per token)
- JWT tokens expire after 24 hours (HS256)
- GitHub webhook signatures validated with HMAC-SHA256 in constant time
- Slack webhook signatures validated with HMAC-SHA256 + 5-minute replay window
- Rate limiting on all API endpoints (60 req/min default, 30 for queries)
- All database queries use parameterised statements (SQLAlchemy ORM / `text()`)

---

## License

MIT — see [LICENSE](LICENSE).
