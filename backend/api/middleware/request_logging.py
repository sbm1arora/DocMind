import time, structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(method=request.method, path=request.url.path)
        try:
            response = await call_next(request)
            logger.info("http.request", status_code=response.status_code,
                        latency_ms=int((time.monotonic() - start) * 1000))
            return response
        except Exception as exc:
            logger.error("http.request.error", error=str(exc),
                         latency_ms=int((time.monotonic() - start) * 1000))
            raise
