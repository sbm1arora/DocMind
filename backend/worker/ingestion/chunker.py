"""
Semantic chunker — splits parsed content into token-bounded chunks.

Rules:
- Max 512 tokens per chunk (MAX_CHUNK_TOKENS)
- Min 50 tokens (MIN_CHUNK_TOKENS) — discard below this
- 64-token overlap between consecutive prose chunks (CHUNK_OVERLAP_TOKENS)
- Code symbols (functions/classes) are kept whole if ≤ MAX_CHUNK_TOKENS, split otherwise
- Chunk types: "section", "function", "class", "prose"
"""

import tiktoken
from dataclasses import dataclass, field

from shared.constants import MAX_CHUNK_TOKENS, MIN_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS
from worker.ingestion.parsers.markdown_parser import ParsedSection
from worker.ingestion.parsers.code_parser import ParsedSymbol

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text))


def split_by_tokens(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Split text into overlapping token windows."""
    tokens = _enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(_enc.decode(chunk_tokens))
        if end == len(tokens):
            break
        start = end - overlap
    return chunks


@dataclass
class Chunk:
    content: str
    chunk_type: str
    chunk_index: int
    start_line: int
    end_line: int
    token_count: int
    symbol_name: str | None = None
    is_public: bool = True
    parent_context: str | None = None
    metadata: dict = field(default_factory=dict)


def chunk_sections(sections: list[ParsedSection]) -> list[Chunk]:
    """Chunk parsed markdown sections into token-bounded prose chunks."""
    chunks: list[Chunk] = []
    index = 0

    for section in sections:
        text = f"{section.title}\n\n{section.content}" if section.title else section.content
        token_count = count_tokens(text)

        if token_count <= MAX_CHUNK_TOKENS:
            if token_count >= MIN_CHUNK_TOKENS:
                chunks.append(Chunk(
                    content=text,
                    chunk_type="section",
                    chunk_index=index,
                    start_line=section.start_line,
                    end_line=section.end_line,
                    token_count=token_count,
                    metadata={"heading_level": section.level},
                ))
                index += 1
        else:
            # Split large sections with overlap
            sub_chunks = split_by_tokens(text, MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS)
            for sub in sub_chunks:
                tc = count_tokens(sub)
                if tc >= MIN_CHUNK_TOKENS:
                    chunks.append(Chunk(
                        content=sub,
                        chunk_type="prose",
                        chunk_index=index,
                        start_line=section.start_line,
                        end_line=section.end_line,
                        token_count=tc,
                        metadata={"heading_level": section.level},
                    ))
                    index += 1

    return chunks


def chunk_symbols(symbols: list[ParsedSymbol], file_path: str) -> list[Chunk]:
    """Chunk parsed code symbols. Keep whole if fits, split if too large."""
    chunks: list[Chunk] = []
    index = 0

    for sym in symbols:
        header = f"# {sym.symbol_type}: {sym.name}"
        if sym.docstring:
            header += f"\n# {sym.docstring}"
        text = f"{header}\n\n{sym.content}"
        token_count = count_tokens(text)

        if token_count <= MAX_CHUNK_TOKENS:
            if token_count >= MIN_CHUNK_TOKENS:
                chunks.append(Chunk(
                    content=text,
                    chunk_type=sym.symbol_type,
                    chunk_index=index,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    token_count=token_count,
                    symbol_name=sym.name,
                    is_public=sym.is_public,
                    metadata={"file_path": file_path},
                ))
                index += 1
        else:
            sub_chunks = split_by_tokens(sym.content, MAX_CHUNK_TOKENS, CHUNK_OVERLAP_TOKENS)
            for i, sub in enumerate(sub_chunks):
                tc = count_tokens(sub)
                if tc >= MIN_CHUNK_TOKENS:
                    chunks.append(Chunk(
                        content=sub,
                        chunk_type=sym.symbol_type,
                        chunk_index=index,
                        start_line=sym.start_line,
                        end_line=sym.end_line,
                        token_count=tc,
                        symbol_name=sym.name,
                        is_public=sym.is_public,
                        parent_context=header,
                        metadata={"file_path": file_path, "part": i},
                    ))
                    index += 1

    return chunks
