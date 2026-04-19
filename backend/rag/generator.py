"""
Claude generation — answers queries using retrieved chunks as context.

Model: claude-sonnet-4-6
Returns: answer text, citations list, confidence score, follow-up suggestions.
"""

import structlog
import anthropic

from api.config import settings
from shared.constants import GENERATION_MODEL

logger = structlog.get_logger()

_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

_SYSTEM_PROMPT = """You are DocMind, an expert documentation assistant. You answer questions about codebases using only the provided code and documentation context.

Rules:
- Answer only from the provided context. Do not hallucinate.
- Be concise and specific. Include code snippets when helpful.
- Always cite sources using the format [source: file_path:line_range].
- End with 2-3 follow-up questions the user might want to ask.
- If the context is insufficient to answer confidently, say so explicitly.
- Confidence: rate your answer 0.0-1.0 based on how well the context supports it."""

_USER_TEMPLATE = """Question: {query}

Context chunks:
{context}

Respond in this exact JSON format:
{{
  "answer": "your detailed answer here",
  "citations": ["file_path:line_range", ...],
  "confidence": 0.0-1.0,
  "follow_ups": ["question 1?", "question 2?", "question 3?"]
}}"""


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        payload = chunk["payload"]
        file_path = payload.get("file_path", "unknown")
        content = payload.get("content", "")
        symbol = payload.get("symbol_name", "")
        label = f"{file_path}" + (f" [{symbol}]" if symbol else "")
        parts.append(f"[{i}] {label}\n{content}")
    return "\n\n---\n\n".join(parts)


async def generate_answer(query: str, chunks: list[dict]) -> dict:
    """Generate a grounded answer from retrieved chunks."""
    if not chunks:
        return {
            "answer": "No relevant documentation found for this query.",
            "citations": [],
            "confidence": 0.0,
            "follow_ups": [],
        }

    context = _format_context(chunks)
    prompt = _USER_TEMPLATE.format(query=query, context=context)

    try:
        import json
        response = await _client.messages.create(
            model=GENERATION_MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Parse JSON response
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        return {
            "answer": result.get("answer", ""),
            "citations": result.get("citations", []),
            "confidence": float(result.get("confidence", 0.5)),
            "follow_ups": result.get("follow_ups", []),
        }

    except Exception as e:
        logger.error("generator.failed", error=str(e))
        return {
            "answer": "Failed to generate answer. Please try again.",
            "citations": [],
            "confidence": 0.0,
            "follow_ups": [],
        }
