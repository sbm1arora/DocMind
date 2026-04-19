import time
import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from api.config import settings
from shared.constants import REDIS_PREFIX_RATE_LIMIT, RATE_LIMIT_DEFAULT

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = RATE_LIMIT_DEFAULT):
        super().__init__(app)
        self.rpm = requests_per_minute
        self.redis = aioredis.from_url(settings.redis_url)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        key = f"{REDIS_PREFIX_RATE_LIMIT}{client_ip}"
        now = int(time.time())
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, now - 60)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, 60)
        results = await pipe.execute()
        if results[2] > self.rpm:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded."})
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rpm)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.rpm - results[2]))
        return response
