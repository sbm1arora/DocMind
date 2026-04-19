"""
JWT utilities — create and validate HS256 access tokens for the DocMind API.

Tokens carry a single claim: {"sub": user_id} and expire after JWT_EXPIRY_HOURS (24h).
"""

from datetime import datetime, timedelta, timezone

import jwt

from api.config import settings
from shared.constants import JWT_ALGORITHM, JWT_EXPIRY_HOURS
from shared.exceptions import AuthenticationError


def create_access_token(user_id: str) -> str:
    """
    Create a signed JWT for the given user ID.

    Args:
        user_id: The UUID of the authenticated user (stored in the "sub" claim).

    Returns:
        A signed JWT string valid for JWT_EXPIRY_HOURS hours.
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)},
        settings.app_secret_key,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT, returning its payload.

    Args:
        token: The raw JWT string from the Authorization header.

    Returns:
        The decoded payload dict (includes "sub", "exp", "iat").

    Raises:
        AuthenticationError: If the token is expired or otherwise invalid.
    """
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")
