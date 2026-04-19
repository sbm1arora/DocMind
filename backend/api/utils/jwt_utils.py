from datetime import datetime, timedelta, timezone
import jwt
from api.config import settings
from shared.constants import JWT_ALGORITHM, JWT_EXPIRY_HOURS
from shared.exceptions import AuthenticationError

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    return jwt.encode({"sub": user_id, "exp": expire, "iat": datetime.now(timezone.utc)},
                      settings.app_secret_key, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid token")
