"""
Database session management.
Provides async session factory and dependency for FastAPI.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings

# Import all models to register them with Base.metadata
# This ensures FK relationships can be resolved across tables.
import src.infrastructure.database.models  # noqa: F401

from src.infrastructure.database.audit_listener import register_audit_listener

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=False,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Register automatic audit logging on all session events
register_audit_listener()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency providing a database session per request."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
