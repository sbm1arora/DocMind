"""
Tests for the RAG pipeline components with all external services mocked.

Covers:
  - rag/fusion.py   — RRF merging + deduplication
  - rag/generator.py — answer generation (Anthropic mocked)
  - rag/pipeline.py  — full pipeline orchestration (all services mocked)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from rag.fusion import reciprocal_rank_fusion
from rag.generator import generate_answer


# ── RRF Fusion ────────────────────────────────────────────────────────────────

class TestRRFFusion:
    def _result(self, id: str, score: float, content: str = "chunk") -> dict:
        return {"id": id, "score": score, "payload": {"content": content, "project_id": "p1"}}

    def test_empty_inputs(self):
        assert reciprocal_rank_fusion([], []) == []

    def test_dense_only(self):
        dense = [self._result("a", 0.9), self._result("b", 0.8)]
        merged = reciprocal_rank_fusion(dense, [])
        assert len(merged) == 2
        ids = [r["id"] for r in merged]
        assert "a" in ids and "b" in ids

    def test_deduplication(self):
        """Same ID appearing in both lists must appear only once in output."""
        dense = [self._result("shared", 0.9), self._result("only_dense", 0.8)]
        sparse = [self._result("shared", 0.85), self._result("only_sparse", 0.7)]
        merged = reciprocal_rank_fusion(dense, sparse)
        ids = [r["id"] for r in merged]
        assert ids.count("shared") == 1

    def test_top_k_respected(self):
        dense = [self._result(str(i), float(i) / 10) for i in range(10)]
        merged = reciprocal_rank_fusion(dense, [], top_k=3)
        assert len(merged) <= 3

    def test_scores_are_positive(self):
        dense = [self._result("x", 0.5)]
        merged = reciprocal_rank_fusion(dense, [])
        assert all(r["score"] > 0 for r in merged)

    def test_higher_ranked_gets_higher_fused_score(self):
        """Item ranked first in dense should outrank item ranked second."""
        dense = [self._result("first", 1.0), self._result("second", 0.5)]
        merged = reciprocal_rank_fusion(dense, [])
        assert merged[0]["id"] == "first"

    def test_dense_weighted_more_than_sparse(self):
        """
        An item appearing first in dense only should score >= item appearing
        first in sparse only, since DENSE_WEIGHT (0.6) > SPARSE_WEIGHT (0.4).
        """
        dense = [self._result("dense_top", 1.0)]
        sparse = [self._result("sparse_top", 1.0)]
        merged = reciprocal_rank_fusion(dense, sparse)
        ids = [r["id"] for r in merged]
        dense_pos = ids.index("dense_top")
        sparse_pos = ids.index("sparse_top")
        assert dense_pos <= sparse_pos


# ── Generator ─────────────────────────────────────────────────────────────────

class TestGenerateAnswer:
    def _chunk(self, content: str, file: str = "src/main.py") -> dict:
        return {
            "id": "chunk-1",
            "score": 0.9,
            "payload": {
                "content": content,
                "file_path": file,
                "symbol_name": "my_func",
                "project_id": "proj-1",
            },
        }

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_no_results(self):
        result = await generate_answer("What does this do?", [])
        assert result["answer"] == "No relevant documentation found for this query."
        assert result["confidence"] == 0.0
        assert result["citations"] == []

    @pytest.mark.asyncio
    async def test_with_chunks_calls_anthropic(self):
        """When chunks are present, Claude is called and result is parsed."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({
                "answer": "This function does X.",
                "citations": ["src/main.py:1-10"],
                "confidence": 0.9,
                "follow_ups": ["What about Y?", "How to configure Z?"],
            })
        )]

        with patch("rag.generator._client") as mock_client:
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            result = await generate_answer(
                "What does my_func do?",
                [self._chunk("def my_func(): return 42")],
            )

        assert result["answer"] == "This function does X."
        assert result["confidence"] == 0.9
        assert "src/main.py:1-10" in result["citations"]

    @pytest.mark.asyncio
    async def test_api_failure_returns_error_dict(self):
        """When Anthropic throws, generate_answer must return a safe error dict."""
        with patch("rag.generator._client") as mock_client:
            mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))
            result = await generate_answer(
                "query", [self._chunk("content")]
            )

        assert "Failed" in result["answer"] or result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_malformed_json_in_response(self):
        """Generator must handle Claude returning non-JSON gracefully."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is plain text, not JSON.")]

        with patch("rag.generator._client") as mock_client:
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            result = await generate_answer(
                "query", [self._chunk("content")]
            )
        # Should not raise — must return a safe fallback
        assert isinstance(result, dict)
        assert "answer" in result


# ── Full Pipeline (integration-style, all services mocked) ───────────────────

class TestRAGPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_returns_expected_keys(self, db_session):
        """Full pipeline must return a dict with all required keys."""
        mock_dense = [
            {"id": "c1", "score": 0.9, "payload": {"content": "def foo(): pass", "file_path": "a.py", "symbol_name": "foo"}},
        ]
        mock_sparse: list = []
        mock_reranked = mock_dense
        mock_generated = {
            "answer": "foo is a function.",
            "citations": ["a.py:1"],
            "confidence": 0.85,
            "follow_ups": ["What does foo return?"],
        }

        with (
            patch("rag.pipeline.dense_search", return_value=mock_dense) as _,
            patch("rag.pipeline.sparse_search", return_value=mock_sparse) as _,
            patch("rag.pipeline.rerank", return_value=mock_reranked) as _,
            patch("rag.pipeline.generate_answer", return_value=mock_generated) as _,
        ):
            from rag.pipeline import run_rag_pipeline
            result = await run_rag_pipeline(
                query="What is foo?",
                project_id="test-project-id",
                db=db_session,
            )

        assert "answer" in result
        assert "citations" in result
        assert "confidence" in result
        assert "chunks_used" in result
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_pipeline_latency_is_positive(self, db_session):
        with (
            patch("rag.pipeline.dense_search", return_value=[]),
            patch("rag.pipeline.sparse_search", return_value=[]),
            patch("rag.pipeline.rerank", return_value=[]),
            patch("rag.pipeline.generate_answer", return_value={
                "answer": "Nothing found.", "citations": [], "confidence": 0.0, "follow_ups": []
            }),
        ):
            from rag.pipeline import run_rag_pipeline
            result = await run_rag_pipeline("query", "proj", db_session)

        assert result["latency_ms"] >= 0
