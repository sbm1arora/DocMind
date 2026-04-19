"""
Markdown/text document parser.

Extracts sections, headings, and content from .md, .mdx, .rst, .txt files.
Returns a list of ParsedSection objects ready for chunking.
"""

import re
from dataclasses import dataclass, field


@dataclass
class ParsedSection:
    title: str
    content: str
    level: int  # heading level (0 = no heading / root)
    start_line: int
    end_line: int
    metadata: dict = field(default_factory=dict)


def parse_markdown(content: str, file_path: str) -> list[ParsedSection]:
    """Parse markdown into sections split on headings."""
    lines = content.splitlines()
    sections: list[ParsedSection] = []
    current_title = file_path
    current_level = 0
    current_lines: list[str] = []
    current_start = 0

    heading_re = re.compile(r"^(#{1,6})\s+(.*)")

    for i, line in enumerate(lines):
        m = heading_re.match(line)
        if m:
            # Flush current section
            if current_lines:
                sections.append(ParsedSection(
                    title=current_title,
                    content="\n".join(current_lines).strip(),
                    level=current_level,
                    start_line=current_start,
                    end_line=i - 1,
                ))
            current_title = m.group(2).strip()
            current_level = len(m.group(1))
            current_lines = []
            current_start = i
        else:
            current_lines.append(line)

    # Flush last section
    if current_lines:
        sections.append(ParsedSection(
            title=current_title,
            content="\n".join(current_lines).strip(),
            level=current_level,
            start_line=current_start,
            end_line=len(lines) - 1,
        ))

    # Drop empty sections
    return [s for s in sections if s.content]


def parse_text(content: str, file_path: str) -> list[ParsedSection]:
    """Plain text — treat entire file as a single section."""
    lines = content.splitlines()
    return [ParsedSection(
        title=file_path.split("/")[-1],
        content=content.strip(),
        level=0,
        start_line=0,
        end_line=len(lines) - 1,
    )] if content.strip() else []


def parse_doc_file(content: str, file_path: str) -> list[ParsedSection]:
    ext = file_path.rsplit(".", 1)[-1].lower()
    if ext in ("md", "mdx"):
        return parse_markdown(content, file_path)
    return parse_text(content, file_path)
