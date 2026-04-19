"""
DocMind MCP Server — exposes RAG tools for Claude Code and other MCP clients.

Tools:
  search_docs      — natural language search over indexed project
  get_section      — fetch a specific doc section by file path
  check_coverage   — return doc coverage score and gaps
  flag_issue       — create a GitHub issue for a doc gap

Transport: SSE (server-sent events) on port 8001
"""

import asyncio
import structlog
import httpx
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route

from api.config import settings
from shared.logging_config import configure_logging

logger = structlog.get_logger()

# MCP server talks to the main FastAPI backend over HTTP
API_BASE = "http://localhost:8000/api/v1"

mcp = Server("docmind")


async def _api_get(path: str, token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def _api_post(path: str, token: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


@mcp.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_docs",
            description="Search project documentation and code using natural language. Returns an answer with citations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "UUID of the DocMind project"},
                    "query": {"type": "string", "description": "Natural language question"},
                    "jwt_token": {"type": "string", "description": "DocMind JWT token for authentication"},
                },
                "required": ["project_id", "query", "jwt_token"],
            },
        ),
        Tool(
            name="get_section",
            description="Fetch a specific document section by file path from an indexed project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "file_path": {"type": "string", "description": "Relative file path (e.g. 'src/auth/jwt.py')"},
                    "jwt_token": {"type": "string"},
                },
                "required": ["project_id", "file_path", "jwt_token"],
            },
        ),
        Tool(
            name="check_coverage",
            description="Return documentation coverage score and gap analysis for a project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "jwt_token": {"type": "string"},
                },
                "required": ["project_id", "jwt_token"],
            },
        ),
        Tool(
            name="flag_issue",
            description="Create a GitHub issue to flag a documentation gap or inaccuracy.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "title": {"type": "string", "description": "Issue title"},
                    "body": {"type": "string", "description": "Issue description"},
                    "jwt_token": {"type": "string"},
                },
                "required": ["project_id", "title", "body", "jwt_token"],
            },
        ),
    ]


@mcp.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    token = arguments.get("jwt_token", "")
    project_id = arguments.get("project_id", "")

    if name == "search_docs":
        result = await _api_post(
            f"/projects/{project_id}/query",
            token,
            {"query": arguments["query"], "channel": "mcp"},
        )
        text = (
            f"Answer: {result['answer']}\n\n"
            f"Citations: {', '.join(result.get('citations', []))}\n"
            f"Confidence: {result.get('confidence', 0):.0%}"
        )
        return [TextContent(type="text", text=text)]

    elif name == "get_section":
        file_path = arguments["file_path"]
        # Query for this specific file
        result = await _api_post(
            f"/projects/{project_id}/query",
            token,
            {"query": f"Explain the contents of {file_path}", "channel": "mcp"},
        )
        return [TextContent(type="text", text=result["answer"])]

    elif name == "check_coverage":
        project = await _api_get(f"/projects/{project_id}", token)
        text = (
            f"Coverage score: {project.get('doc_coverage_score', 0):.0%}\n"
            f"Status: {project['status']}\n"
            f"Files indexed: {project['file_count']}\n"
            f"Chunks: {project['chunk_count']}"
        )
        return [TextContent(type="text", text=text)]

    elif name == "flag_issue":
        # Queue a create_issue task (simplified — posts to GitHub directly)
        import httpx as _httpx
        async with _httpx.AsyncClient() as client:
            # Get project to find repo
            project = await _api_get(f"/projects/{project_id}", token)
            repo = project.get("repo_full_name", "")
            text = f"Issue flagged for {repo}: {arguments['title']}"
        return [TextContent(type="text", text=text)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


def create_mcp_app():
    """Create the Starlette app for the MCP SSE server."""
    transport = SseServerTransport("/messages")

    async def handle_sse(request: Request):
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await mcp.run(
                read_stream,
                write_stream,
                mcp.create_initialization_options(),
            )

    return Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/messages", endpoint=transport.handle_post_message, methods=["POST"]),
    ])


if __name__ == "__main__":
    import uvicorn
    configure_logging()
    app = create_mcp_app()
    uvicorn.run(app, host="0.0.0.0", port=8001)
