"""
Writer Agent — generates README, API_REFERENCE, ARCHITECTURE, GETTING_STARTED
from indexed project chunks using Claude.
"""

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

DOC_PROMPTS = {
    "readme": """Generate a comprehensive README.md for this project. Include:
- Project name and description
- Key features
- Installation instructions
- Usage examples with code
- Configuration options
- Contributing guidelines

Base it entirely on the code and documentation context provided.""",

    "api_reference": """Generate a complete API_REFERENCE.md. For every public function, class, and method found in the context:
- Function/class name with full signature
- Description of what it does
- Parameters with types and descriptions
- Return value with type
- Usage example

Format each entry clearly. Base it entirely on the code context provided.""",

    "architecture": """Generate an ARCHITECTURE.md explaining:
- System overview and purpose
- Module/package responsibilities
- Key data flows between components
- Design decisions and patterns used
- Dependency relationships

Base it entirely on the code structure and documentation provided.""",

    "getting_started": """Generate a GETTING_STARTED.md guide including:
- Prerequisites and system requirements
- Step-by-step installation
- First steps / quickstart
- Common tasks with examples
- Troubleshooting common issues

Base it entirely on the project context provided.""",
}


class WriterAgent(BaseAgent):
    name = "writer"

    async def execute(self, task: AgentTask, db: AsyncSession) -> dict:
        project_id = str(task.project_id)
        doc_types = task.input.get("doc_types", list(DOC_PROMPTS.keys()))

        # Fetch representative chunks for context
        result = await db.execute(
            select(Chunk)
            .where(Chunk.project_id == project_id, Chunk.is_public == True)
            .order_by(Chunk.token_count.desc())
            .limit(50)
        )
        chunks = result.scalars().all()

        if not chunks:
            return {"error": "No indexed content found", "documents": []}

        context = "\n\n---\n\n".join(
            f"[{c.chunk_type}] {c.symbol_name or ''}\n{c.content[:800]}"
            for c in chunks
        )

        generated = []
        for doc_type in doc_types:
            if doc_type not in DOC_PROMPTS:
                continue

            try:
                response = await _client.messages.create(
                    model=GENERATION_MODEL,
                    max_tokens=4096,
                    messages=[{
                        "role": "user",
                        "content": f"{DOC_PROMPTS[doc_type]}\n\n## Project Context\n\n{context}",
                    }],
                )
                content = response.content[0].text

                # Save to documents table
                doc = Document(
                    project_id=project_id,
                    file_path=f"docs/{doc_type.upper()}.md",
                    doc_type="generated",
                    generated_type=doc_type,
                    title=doc_type.replace("_", " ").title(),
                    content_raw=content,
                    status="current",
                )
                db.add(doc)
                await db.flush()
                generated.append({"doc_type": doc_type, "document_id": str(doc.id)})
                logger.info("writer.doc_generated", doc_type=doc_type, project_id=project_id)

            except Exception as e:
                logger.error("writer.doc_failed", doc_type=doc_type, error=str(e))
                generated.append({"doc_type": doc_type, "error": str(e)})

        await db.commit()
        return {"documents": generated}
