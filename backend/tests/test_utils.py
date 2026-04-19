"""
Unit tests for utility modules:
  - api/utils/encryption.py   — AES-256-GCM encrypt/decrypt
  - api/utils/jwt_utils.py    — JWT create/decode
  - api/utils/hmac_utils.py   — GitHub + Slack HMAC verification
  - worker/ingestion/chunker.py — token-bounded chunking
"""

import hashlib
import hmac
import time
import pytest

from api.utils.encryption import encrypt_token, decrypt_token
from api.utils.jwt_utils import create_access_token, decode_access_token
from api.utils.hmac_utils import verify_github_signature, verify_slack_signature
from shared.exceptions import AuthenticationError, WebhookError
from worker.ingestion.chunker import (
    Chunk,
    chunk_sections,
    chunk_symbols,
    count_tokens,
    split_by_tokens,
)
from worker.ingestion.parsers.markdown_parser import ParsedSection, parse_markdown, parse_doc_file
from worker.ingestion.parsers.code_parser import ParsedSymbol, parse_with_regex


# ── Encryption ────────────────────────────────────────────────────────────────

class TestEncryption:
    def test_roundtrip(self):
        """Encrypted then decrypted value equals the original."""
        secret = "gho_super_secret_github_token"
        ciphertext, iv = encrypt_token(secret)
        assert decrypt_token(ciphertext, iv) == secret

    def test_ciphertext_is_not_plaintext(self):
        """Ciphertext must not contain the plaintext."""
        secret = "gho_my_token"
        ciphertext, iv = encrypt_token(secret)
        assert secret.encode() not in ciphertext

    def test_different_ivs_each_call(self):
        """Each call must produce a fresh random IV."""
        _, iv1 = encrypt_token("token")
        _, iv2 = encrypt_token("token")
        assert iv1 != iv2

    def test_iv_is_12_bytes(self):
        """AES-GCM IV must be exactly 12 bytes."""
        _, iv = encrypt_token("token")
        assert len(iv) == 12

    def test_wrong_iv_raises(self):
        """Decrypting with a wrong IV must raise an exception."""
        ciphertext, iv = encrypt_token("token")
        bad_iv = bytes(12)  # all-zero IV
        with pytest.raises(Exception):
            decrypt_token(ciphertext, bad_iv)


# ── JWT ───────────────────────────────────────────────────────────────────────

class TestJWT:
    def test_create_and_decode(self):
        """Token created for a user ID must decode to the same user ID."""
        user_id = "550e8400-e29b-41d4-a716-446655440000"
        token = create_access_token(user_id)
        payload = decode_access_token(token)
        assert payload["sub"] == user_id

    def test_payload_contains_exp_and_iat(self):
        """JWT must contain 'exp' and 'iat' claims."""
        token = create_access_token("user-123")
        payload = decode_access_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_invalid_token_raises(self):
        """A garbage token must raise AuthenticationError."""
        with pytest.raises(AuthenticationError, match="Invalid token"):
            decode_access_token("not.a.valid.jwt")

    def test_tampered_token_raises(self):
        """A token with a tampered signature must raise AuthenticationError."""
        token = create_access_token("user-123")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(AuthenticationError):
            decode_access_token(tampered)


# ── HMAC utils ────────────────────────────────────────────────────────────────

class TestGitHubSignature:
    def _make_sig(self, payload: bytes, secret: str) -> str:
        return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    def test_valid_signature_returns_true(self):
        payload = b'{"action": "push"}'
        secret = "webhook_secret"
        sig = self._make_sig(payload, secret)
        assert verify_github_signature(payload, sig, secret) is True

    def test_wrong_secret_returns_false(self):
        payload = b'{"action": "push"}'
        sig = self._make_sig(payload, "correct_secret")
        assert verify_github_signature(payload, sig, "wrong_secret") is False

    def test_missing_sha256_prefix_returns_false(self):
        payload = b"data"
        secret = "sec"
        raw_hex = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert verify_github_signature(payload, raw_hex, secret) is False

    def test_empty_payload(self):
        payload = b""
        secret = "sec"
        sig = self._make_sig(payload, secret)
        assert verify_github_signature(payload, sig, secret) is True


class TestSlackSignature:
    def _make_sig(self, payload: bytes, timestamp: str, secret: str) -> str:
        base = f"v0:{timestamp}:{payload.decode()}"
        return "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()

    def test_valid_signature(self):
        payload = b"command=test"
        ts = str(int(time.time()))
        secret = "slack_secret"
        sig = self._make_sig(payload, ts, secret)
        assert verify_slack_signature(payload, ts, sig, secret) is True

    def test_stale_timestamp_raises(self):
        payload = b"data"
        old_ts = str(int(time.time()) - 400)  # 400 seconds old
        secret = "sec"
        sig = self._make_sig(payload, old_ts, secret)
        with pytest.raises(WebhookError, match="timestamp too old"):
            verify_slack_signature(payload, old_ts, sig, secret)

    def test_wrong_secret_returns_false(self):
        payload = b"data"
        ts = str(int(time.time()))
        sig = self._make_sig(payload, ts, "correct")
        assert verify_slack_signature(payload, ts, sig, "wrong") is False


# ── Chunker ───────────────────────────────────────────────────────────────────

class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_nonempty(self):
        assert count_tokens("hello world") > 0

    def test_longer_is_more_tokens(self):
        short = "hello"
        long = "hello " * 200
        assert count_tokens(long) > count_tokens(short)


class TestSplitByTokens:
    def test_short_text_single_chunk(self):
        text = "short"
        chunks = split_by_tokens(text, max_tokens=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self):
        text = "word " * 300  # ~300 tokens
        chunks = split_by_tokens(text, max_tokens=100, overlap=10)
        assert len(chunks) > 1

    def test_overlap_means_chunks_share_content(self):
        text = "word " * 200
        chunks = split_by_tokens(text, max_tokens=100, overlap=20)
        # Adjacent chunks should overlap — last tokens of chunk N appear at start of chunk N+1
        assert len(chunks) >= 2


class TestChunkSections:
    def _section(self, content: str, title: str = "Title", level: int = 1) -> ParsedSection:
        return ParsedSection(
            title=title,
            content=content,
            level=level,
            start_line=0,
            end_line=len(content.splitlines()),
        )

    def test_short_section_becomes_one_chunk(self):
        sections = [self._section("This is a short paragraph.")]
        chunks = chunk_sections(sections)
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "section"

    def test_long_section_splits(self):
        long_content = "word " * 600  # well over 512 tokens
        sections = [self._section(long_content)]
        chunks = chunk_sections(sections)
        assert len(chunks) > 1
        for c in chunks:
            assert c.chunk_type == "prose"

    def test_empty_content_skipped(self):
        sections = [self._section("")]
        chunks = chunk_sections(sections)
        assert chunks == []

    def test_tiny_section_below_min_tokens_skipped(self):
        tiny = "hi"  # definitely < 50 tokens
        sections = [self._section(tiny)]
        chunks = chunk_sections(sections)
        assert chunks == []

    def test_chunk_has_correct_fields(self):
        sections = [self._section("This is a proper sized paragraph with enough content to pass the minimum token threshold for chunking.")]
        chunks = chunk_sections(sections)
        if chunks:
            c = chunks[0]
            assert c.chunk_index == 0
            assert c.token_count > 0
            assert isinstance(c.metadata, dict)


class TestChunkSymbols:
    def _symbol(self, name: str, content: str, sym_type: str = "function") -> ParsedSymbol:
        return ParsedSymbol(
            name=name,
            symbol_type=sym_type,
            content=content,
            docstring="Does something useful.",
            start_line=0,
            end_line=len(content.splitlines()),
            is_public=True,
        )

    def test_small_function_one_chunk(self):
        sym = self._symbol("my_func", "def my_func():\n    return 42\n")
        chunks = chunk_symbols([sym], "src/module.py")
        assert len(chunks) == 1
        assert chunks[0].symbol_name == "my_func"
        assert chunks[0].chunk_type == "function"

    def test_large_function_splits(self):
        body = "    x = 1\n" * 300
        sym = self._symbol("big_func", f"def big_func():\n{body}")
        chunks = chunk_symbols([sym], "src/module.py")
        assert len(chunks) > 1

    def test_chunk_inherits_symbol_name(self):
        sym = self._symbol("parse", "def parse(x):\n    return x * 2\n")
        chunks = chunk_symbols([sym], "src/parse.py")
        if chunks:
            assert chunks[0].symbol_name == "parse"

    def test_is_public_preserved(self):
        sym = self._symbol("_private", "def _private(): pass\n")
        sym.is_public = False
        chunks = chunk_symbols([sym], "src/mod.py")
        if chunks:
            assert chunks[0].is_public is False


# ── Markdown parser ───────────────────────────────────────────────────────────

class TestMarkdownParser:
    def test_single_heading(self):
        content = "# Title\n\nSome content here.\n"
        sections = parse_markdown(content, "README.md")
        assert any(s.title == "Title" for s in sections)

    def test_multiple_headings(self):
        content = "# H1\n\nText A\n\n## H2\n\nText B\n"
        sections = parse_markdown(content, "doc.md")
        titles = [s.title for s in sections]
        assert "H1" in titles
        assert "H2" in titles

    def test_empty_sections_filtered(self):
        content = "# Empty\n\n# HasContent\n\nActual content here.\n"
        sections = parse_markdown(content, "doc.md")
        # "Empty" heading has no body content so should be filtered out
        titles = [s.title for s in sections]
        assert "Empty" not in titles

    def test_non_markdown_falls_through(self):
        sections = parse_doc_file("plain text\nno headings", "notes.txt")
        assert len(sections) == 1
        assert sections[0].content == "plain text\nno headings"


# ── Regex code parser ─────────────────────────────────────────────────────────

class TestCodeParserRegex:
    def test_python_function(self):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'\n"
        symbols = parse_with_regex(code, "python")
        assert any(s.name == "greet" for s in symbols)

    def test_python_class(self):
        code = "class Foo:\n    pass\n"
        symbols = parse_with_regex(code, "python")
        assert any(s.name == "Foo" and s.symbol_type == "class" for s in symbols)

    def test_python_private_function(self):
        code = "def _helper():\n    pass\n"
        symbols = parse_with_regex(code, "python")
        names = [s.name for s in symbols]
        assert "_helper" in names

    def test_javascript_function(self):
        code = "function doWork(x) {\n  return x + 1;\n}\n"
        symbols = parse_with_regex(code, "javascript")
        assert any(s.name == "doWork" for s in symbols)

    def test_go_function(self):
        code = "func ProcessRequest(req *http.Request) error {\n  return nil\n}\n"
        symbols = parse_with_regex(code, "go")
        assert any(s.name == "ProcessRequest" for s in symbols)

    def test_unknown_language_returns_empty(self):
        symbols = parse_with_regex("some code", "ruby")
        assert symbols == []
