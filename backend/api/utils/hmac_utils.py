import hashlib, hmac, time
from shared.exceptions import WebhookError

def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

def verify_slack_signature(payload: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    if abs(time.time() - float(timestamp)) > 300:
        raise WebhookError("Slack request timestamp too old")
    base = f"v0:{timestamp}:{payload.decode()}"
    expected = "v0=" + hmac.new(signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
