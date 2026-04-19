import structlog
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from api.config import settings
from db.models import Base

logger = structlog.get_logger()

engine = create_async_engine(
    settings.database_url, echo=settings.app_env == "development",
    pool_size=20, max_overflow=10, pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database.initialized")

async def check_db_health() -> bool:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("database.health_check_failed", error=str(e))
        return False

async_session_factory = AsyncSessionLocal
