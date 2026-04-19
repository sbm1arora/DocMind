"""
HMAC signature verification for GitHub and Slack webhooks.

Both platforms sign their webhook payloads with HMAC-SHA256.
These helpers validate the signatures in constant time to prevent
timing attacks.
"""

import hashlib
import hmac
import time

from shared.exceptions import WebhookError


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Validate a GitHub webhook X-Hub-Signature-256 header.

    Args:
        payload: The raw request body bytes.
        signature: The value of the X-Hub-Signature-256 header (e.g. "sha256=abc...").
        secret: The webhook secret configured when the webhook was registered.

    Returns:
        True if the signature is valid, False otherwise.
    """
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_slack_signature(payload: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    """
    Validate a Slack webhook X-Slack-Signature header.

    Also checks that the request timestamp is within 5 minutes to prevent
    replay attacks.

    Args:
        payload: The raw request body bytes.
        timestamp: The X-Slack-Request-Timestamp header value.
        signature: The X-Slack-Signature header value (e.g. "v0=abc...").
        signing_secret: The Slack app signing secret.

    Returns:
        True if the signature is valid, False otherwise.

    Raises:
        WebhookError: If the timestamp is more than 5 minutes old.
    """
    if abs(time.time() - float(timestamp)) > 300:
        raise WebhookError("Slack request timestamp too old")
    base = f"v0:{timestamp}:{payload.decode()}"
    expected = "v0=" + hmac.new(signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
