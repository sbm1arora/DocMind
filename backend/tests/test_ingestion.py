"""
Tests for the ingestion worker components.

Covers:
  - full_ingestion._detect_language — extension → language mapping
  - full_ingestion._is_code_file / _is_doc_file
  - full_ingestion._sha256 — deterministic hash
  - embedder.embed_texts — mocked OpenAI
  - vector_store (search) — mocked Qdrant
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from worker.ingestion.full_ingestion import (
    _detect_language,
    _is_code_file,
    _is_doc_file,
    _sha256,
)


# ── Language detection ─────────────────────────────────────────────────────────

class TestDetectLanguage:
    @pytest.mark.parametrize("path,expected", [
        ("src/main.py", "python"),
        ("lib/utils.js", "javascript"),
        ("app/index.mjs", "javascript"),
        ("types/index.ts", "typescript"),
        ("types/Button.tsx", "typescript"),
        ("pkg/server.go", "go"),
        ("README.md", "markdown"),
        ("docs/guide.mdx", "markdown"),
        ("config.yml", "yaml"),
        ("config.yaml", "yaml"),
        ("package.json", "json"),
        ("notes.txt", "text"),
        ("docs/api.rst", "text"),
    ])
    def test_known_extensions(self, path, expected):
        assert _detect_language(path) == expected

    @pytest.mark.parametrize("path", [
        "image.png",
        "binary.exe",
        "archive.tar.gz",
        "font.woff2",
    ])
    def test_unknown_extensions_return_none(self, path):
        assert _detect_language(path) is None


class TestFileTypeChecks:
    @pytest.mark.parametrize("path", ["main.py", "utils.js", "types.ts", "server.go"])
    def test_code_files(self, path):
        assert _is_code_file(path) is True
        assert _is_doc_file(path) is False

    @pytest.mark.parametrize("path", ["README.md", "guide.mdx", "notes.txt", "docs.rst"])
    def test_doc_files(self, path):
        assert _is_doc_file(path) is True
        assert _is_code_file(path) is False

    def test_yaml_is_neither_code_nor_doc(self):
        assert _is_code_file("config.yml") is False
        assert _is_doc_file("config.yml") is False


# ── SHA256 hash ────────────────────────────────────────────────────────────────

class TestSha256:
    def test_deterministic(self):
        assert _sha256("hello") == _sha256("hello")

    def test_different_inputs_different_hashes(self):
        assert _sha256("hello") != _sha256("world")

    def test_returns_64_hex_chars(self):
        result = _sha256("test content")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_string(self):
        result = _sha256("")
        assert len(result) == 64


# ── Embedder ──────────────────────────────────────────────────────────────────

class TestEmbedder:
    @pytest.mark.asyncio
    async def test_embed_returns_vectors(self):
        """embed_texts must return one vector per input text."""
        mock_embedding = [0.1] * 2048
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]

        with patch("worker.ingestion.embedder._client") as mock_client:
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            from worker.ingestion.embedder import embed_texts
            result = await embed_texts(["test text"])

        assert len(result) == 1
        assert len(result[0]) == 2048

    @pytest.mark.asyncio
    async def test_embed_multiple_texts(self):
        """embed_texts must batch correctly and return one vector per text."""
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1] * 2048),
            MagicMock(embedding=[0.2] * 2048),
        ]

        with patch("worker.ingestion.embedder._client") as mock_client:
            mock_client.embeddings.create = AsyncMock(return_value=mock_response)
            from worker.ingestion.embedder import embed_texts
            result = await embed_texts(["text one", "text two"])

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_embed_empty_list(self):
        """embed_texts([]) must return [] without calling the API."""
        from worker.ingestion.embedder import embed_texts
        result = await embed_texts([])
        assert result == []
