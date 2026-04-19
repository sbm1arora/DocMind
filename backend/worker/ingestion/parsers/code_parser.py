"""
Code parser — extracts functions, classes, and docstrings from source files.

Uses tree-sitter for Python, JavaScript, TypeScript, and Go.
Falls back to regex-based extraction if tree-sitter grammar unavailable.
"""

import re
import structlog
from dataclasses import dataclass, field

logger = structlog.get_logger()


@dataclass
class ParsedSymbol:
    name: str
    symbol_type: str  # "function" | "class" | "method"
    content: str
    docstring: str | None
    start_line: int
    end_line: int
    is_public: bool
    metadata: dict = field(default_factory=dict)


def _is_public(name: str, language: str) -> bool:
    if language == "python":
        return not name.startswith("_")
    if language in ("javascript", "typescript"):
        return True  # export detection handled via metadata
    if language == "go":
        return name[0].isupper() if name else False
    return True


def _extract_python_docstring(node_text: str) -> str | None:
    """Extract first triple-quoted string from a function/class body."""
    m = re.search(r'"""(.*?)"""', node_text, re.DOTALL)
    if not m:
        m = re.search(r"'''(.*?)'''", node_text, re.DOTALL)
    return m.group(1).strip() if m else None


def parse_with_treesitter(content: str, language: str) -> list[ParsedSymbol]:
    """Parse code using tree-sitter grammars."""
    try:
        import tree_sitter_python
        import tree_sitter_javascript
        import tree_sitter_typescript
        import tree_sitter_go
        from tree_sitter import Language, Parser

        lang_map = {
            "python": tree_sitter_python.language(),
            "javascript": tree_sitter_javascript.language(),
            "typescript": tree_sitter_typescript.language_typescript(),
            "go": tree_sitter_go.language(),
        }
        if language not in lang_map:
            return []

        parser = Parser(Language(lang_map[language]))
        tree = parser.parse(content.encode())
        lines = content.splitlines()
        symbols: list[ParsedSymbol] = []

        def extract_name(node) -> str | None:
            for child in node.children:
                if child.type == "identifier":
                    return child.text.decode()
            return None

        def walk(node, depth: int = 0):
            sym_types = {
                "python": ["function_definition", "class_definition"],
                "javascript": ["function_declaration", "class_declaration", "arrow_function", "method_definition"],
                "typescript": ["function_declaration", "class_declaration", "method_definition", "interface_declaration"],
                "go": ["function_declaration", "method_declaration", "type_declaration"],
            }
            if node.type in sym_types.get(language, []):
                name = extract_name(node)
                if name:
                    start = node.start_point[0]
                    end = node.end_point[0]
                    sym_content = "\n".join(lines[start:end + 1])
                    docstring = _extract_python_docstring(sym_content) if language == "python" else None
                    symbols.append(ParsedSymbol(
                        name=name,
                        symbol_type="class" if "class" in node.type else "function",
                        content=sym_content,
                        docstring=docstring,
                        start_line=start,
                        end_line=end,
                        is_public=_is_public(name, language),
                    ))
            for child in node.children:
                walk(child, depth + 1)

        walk(tree.root_node)
        return symbols

    except Exception as e:
        logger.warning("code_parser.treesitter_failed", language=language, error=str(e))
        return parse_with_regex(content, language)


def parse_with_regex(content: str, language: str) -> list[ParsedSymbol]:
    """Fallback regex-based parser for when tree-sitter is unavailable."""
    lines = content.splitlines()
    symbols: list[ParsedSymbol] = []

    patterns = {
        "python": [
            (r"^(async\s+)?def\s+(\w+)\s*\(", "function"),
            (r"^class\s+(\w+)", "class"),
        ],
        "javascript": [
            (r"^(export\s+)?(async\s+)?function\s+(\w+)\s*\(", "function"),
            (r"^(export\s+)?(default\s+)?class\s+(\w+)", "class"),
        ],
        "typescript": [
            (r"^(export\s+)?(async\s+)?function\s+(\w+)\s*[\(<]", "function"),
            (r"^(export\s+)?(abstract\s+)?class\s+(\w+)", "class"),
            (r"^(export\s+)?interface\s+(\w+)", "class"),
        ],
        "go": [
            (r"^func\s+(\w+)\s*\(", "function"),
            (r"^func\s+\(\w+\s+\*?\w+\)\s+(\w+)\s*\(", "function"),
            (r"^type\s+(\w+)\s+struct", "class"),
        ],
    }

    lang_patterns = patterns.get(language, [])
    for i, line in enumerate(lines):
        for pattern, sym_type in lang_patterns:
            m = re.match(pattern, line.strip())
            if m:
                name = m.group(m.lastindex) if m.lastindex else m.group(1)
                # Grab up to 50 lines for context
                end = min(i + 50, len(lines) - 1)
                sym_content = "\n".join(lines[i:end + 1])
                symbols.append(ParsedSymbol(
                    name=name,
                    symbol_type=sym_type,
                    content=sym_content,
                    docstring=None,
                    start_line=i,
                    end_line=end,
                    is_public=_is_public(name, language),
                ))
                break

    return symbols


def parse_code_file(content: str, file_path: str, language: str) -> list[ParsedSymbol]:
    return parse_with_treesitter(content, language)
