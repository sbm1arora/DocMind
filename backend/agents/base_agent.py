"""
Base agent class — Redis task queue consumer.

Agents subscribe to a Redis channel, pick up tasks, execute them,
and update the agent_tasks table with progress and results.
"""

import asyncio
import json
import structlog
from abc import ABC, abstractmethod

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import AsyncSessionLocal
from db.models import AgentTask
from shared.constants import REDIS_CHANNEL_AGENTS

logger = structlog.get_logger()


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, redis: Redis):
        self.redis = redis

    @abstractmethod
    async def execute(self, task: AgentTask, db: AsyncSession) -> dict:
        """Execute the task and return output dict."""
        ...

    async def run_once(self, task_id: str) -> None:
        """Process a single task by ID."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error("agent.task_not_found", task_id=task_id, agent=self.name)
                return

            task.status = "running"
            await db.commit()
            logger.info("agent.task_started", task_id=task_id, agent=self.name)

            try:
                output = await self.execute(task, db)
                task.status = "completed"
                task.output = output
                logger.info("agent.task_completed", task_id=task_id, agent=self.name)
            except Exception as e:
                task.status = "failed"
                task.output = {"error": str(e)}
                logger.error("agent.task_failed", task_id=task_id, agent=self.name, error=str(e), exc_info=True)

            await db.commit()

    async def listen(self) -> None:
        """Listen for tasks on the agents Redis channel."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(REDIS_CHANNEL_AGENTS)
        logger.info("agent.listening", agent=self.name)

        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        if data.get("agent") == self.name or data.get("agent") == "*":
                            task_id = data.get("task_id")
                            if task_id:
                                asyncio.create_task(self.run_once(task_id))
                    except json.JSONDecodeError:
                        pass
        finally:
            await pubsub.unsubscribe(REDIS_CHANNEL_AGENTS)
            await pubsub.aclose()
