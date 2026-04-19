"""
Custom exception hierarchy for DocMind.

All domain exceptions extend DocMindError so callers can catch the base
class when needed. FastAPI exception handlers in main.py map each subclass
to the appropriate HTTP status code.
"""


class DocMindError(Exception):
    """Base class for all DocMind application errors."""


class NotFoundError(DocMindError):
    """Raised when a requested resource does not exist (→ HTTP 404)."""


class AuthenticationError(DocMindError):
    """Raised when a request cannot be authenticated (→ HTTP 401)."""


class AuthorizationError(DocMindError):
    """Raised when an authenticated user lacks permission (→ HTTP 403)."""


class ValidationError(DocMindError):
    """Raised when request data fails business-logic validation (→ HTTP 422)."""


class GitHubError(DocMindError):
    """Raised when a GitHub API call fails."""


class IngestionError(DocMindError):
    """Raised when repository ingestion fails."""


class EmbeddingError(DocMindError):
    """Raised when the embedding service returns an error."""


class GenerationError(DocMindError):
    """Raised when the LLM generation step fails."""


class WebhookError(DocMindError):
    """Raised when an incoming webhook payload is invalid (→ HTTP 400)."""


class RateLimitError(DocMindError):
    """Raised when a client exceeds the rate limit (→ HTTP 429)."""
