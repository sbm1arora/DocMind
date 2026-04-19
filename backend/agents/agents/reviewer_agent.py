"""
Reviewer Agent — validates generated doc accuracy against actual code chunks.
Computes a quality score on 5 dimensions and flags inaccuracies.
"""

import json
import structlog
import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from agents.base_agent import BaseAgent
from api.config import settings
from db.models import AgentTask, Document, Chunk
from shared.constants import GENERATION_MODEL

logger = structlog.get_logger()

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_REVIEW_PROMPT = """You are a code documentation reviewer. Compare the generated documentation against the actual code context and evaluate quality.

Score each dimension 0.0-1.0:
1. accuracy — Does the doc correctly describe what the code does?
2. completeness — Does it cover all major functions/features?
3. clarity — Is it easy to understand for a developer unfamiliar with the code?
4. examples — Are code examples correct and useful?
5. currency — Does it reflect the current code structure (no outdated references)?

Respond in JSON:
{
  "scores": {"accuracy": 0.0, "completeness": 0.0, "clarity": 0.0, "examples": 0.0, "currency": 0.0},
  "overall": 0.0,
  "issues": ["list of specific issues found"],
  "suggestions": ["list of improvement suggestions"]
}"""


class ReviewerAgent(BaseAgent):
    name = "reviewer"

    async def execute(self, task: AgentTask, db: AsyncSession) -> dict:
        project_id = str(task.project_id)
        document_id = task.input.get("document_id")

        if not document_id:
            return {"error": "document_id required in task input"}

        # Fetch the document
        doc_result = await db.execute(select(Document).where(Document.id == document_id))
        doc = doc_result.scalar_one_or_none()
        if not doc:
            return {"error": f"Document {document_id} not found"}

        # Fetch code chunks for cross-reference
        chunks_result = await db.execute(
            select(Chunk)
            .where(Chunk.project_id == project_id, Chunk.chunk_type.in_(["function", "class"]))
            .limit(30)
        )
        chunks = chunks_result.scalars().all()
        code_context = "\n\n---\n\n".join(
            f"[{c.chunk_type}] {c.symbol_name}\n{c.content[:600]}"
            for c in chunks
        )

        try:
            response = await _client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": (
                        f"{_REVIEW_PROMPT}\n\n"
                        f"## Generated Documentation\n\n{doc.content_raw[:3000]}\n\n"
                        f"## Actual Code\n\n{code_context}"
                    ),
                }],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)

            scores = result.get("scores", {})
            overall = result.get("overall", sum(scores.values()) / max(len(scores), 1))

            # Update document with quality score
            doc.quality_score = overall
            doc.quality_details = result
            await db.commit()

            return {
                "document_id": document_id,
                "overall_score": overall,
                "scores": scores,
                "issues": result.get("issues", []),
                "suggestions": result.get("suggestions", []),
            }

        except Exception as e:
            logger.error("reviewer.failed", document_id=document_id, error=str(e))
            return {"error": str(e)}
