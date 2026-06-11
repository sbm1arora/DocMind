# Changelog

Notable changes to DocMind, newest first. Entries describe effects, not commits.

## [Unreleased]

- docs: add CLAUDE.md (agent guide, behavioral contract, risk-class list)
- docs: add AGENTS.md
- docs: fix stale claims in README (Next.js label, query rate-limit note)
- docs: archive ENGINEERING_SPEC.md and STATUS.md to docs/archive/

## [1.0.0] — 2026-04-29

- Initial complete implementation: all 9 phases shipped
- FastAPI backend with GitHub OAuth, JWT auth, AES-256-GCM token encryption
- Full RAG pipeline: Qdrant dense + PG FTS sparse → RRF fusion → Cohere rerank → Claude generation
- Ingestion worker: tree-sitter parsing, tiktoken chunking, OpenAI embeddings
- Agent system: WriterAgent, ReviewerAgent, QualityCritic, PRCreator
- GitHub webhook handler for incremental re-indexing
- MCP SSE server with 4 tools (search_docs, get_section, check_coverage, flag_issue)
- Slack + WhatsApp (Twilio) integration endpoints
- Next.js 16 + React 19 frontend: landing, dashboard, chat UI, doc viewer
- Docker Compose for full local stack (PostgreSQL 16, Redis 7, Qdrant, API, Worker, MCP, Frontend)
- 7-file pytest test suite
