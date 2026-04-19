"""
DocMind Ingestion Worker

Subscribes to Redis pub/sub channels and dispatches ingestion jobs.
Runs as a separate process alongside the FastAPI server.

Usage: python -m worker.worker_main
"""

import asyncio
import json
import os
import signal
import structlog
from redis.asyncio import Redis

from api.config import settings
from shared.constants import REDIS_CHANNEL_INGESTION
from shared.logging_config import configure_logging
from worker.ingestion.full_ingestion import handle_full_ingestion
from worker.ingestion.incremental_ingestion import handle_incremental_ingestion

logger = structlog.get_logger()

_shutdown = asyncio.Event()


def _handle_signal(signum, frame):
    logger.info("worker.signal_received", signal=signum)
    _shutdown.set()


async def dispatch(redis: Redis, event: str, payload: dict) -> None:
    try:
        if event == "ingestion:start":
            await handle_full_ingestion(redis, payload["project_id"])
        elif event == "ingestion:incremental":
            await handle_incremental_ingestion(
                redis,
                payload["project_id"],
                payload["before_sha"],
                payload["after_sha"],
            )
        else:
            logger.warning("worker.unknown_event", event=event)
    except Exception as e:
        logger.error("worker.dispatch_error", event=event, error=str(e), exc_info=True)


async def run() -> None:
    configure_logging()
    logger.info("worker.starting", channels=[REDIS_CHANNEL_INGESTION])

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(REDIS_CHANNEL_INGESTION)

    try:
        while not _shutdown.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    event = data.get("event", "")
                    logger.info("worker.received", event=event)
                    asyncio.create_task(dispatch(redis, event, data))
                except json.JSONDecodeError as e:
                    logger.error("worker.bad_message", error=str(e), raw=message["data"])
    finally:
        await pubsub.unsubscribe(REDIS_CHANNEL_INGESTION)
        await pubsub.aclose()
        await redis.aclose()
        logger.info("worker.stopped")


if __name__ == "__main__":
    asyncio.run(run())
