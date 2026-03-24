from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

from app.config import settings


def fix_db_url(url: str) -> str:
    """Fix Render PostgreSQL URL format (postgres:// → postgresql+asyncpg://)."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _build_engine():
    url = fix_db_url(settings.database_url)
    is_sqlite = url.startswith("sqlite")

    if is_sqlite:
        return create_async_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=settings.debug,
        )
    else:
        return create_async_engine(
            url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )


class Base(DeclarativeBase):
    pass


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that provides a database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables defined in Base metadata."""
    # Import all models so they are registered with Base before create_all
    import app.auth.models  # noqa: F401
    import app.audit  # noqa: F401

    # Lazy-import optional module models so missing modules don't block startup
    _optional_modules = [
        "app.programs.models",
        "app.contracts.models",
        "app.counterparties.models",
        "app.assets.models",
        "app.grid.models",
        "app.dispatch.models",
        "app.settlement.models",
        "app.forecasting.models",
        "app.optimization.models",
        "app.integrations.config_mgr.models",
        "app.aggregator.models",
        "app.lv_network.models",
        "app.scada_gateway.models",
    ]
    for mod in _optional_modules:
        try:
            __import__(mod)
        except ModuleNotFoundError:
            pass

    async with engine.begin() as conn:
        # Drop stale FK constraints that were created in earlier deploys.
        # These are no-ops if the constraints don't exist (IF EXISTS).
        is_pg = not fix_db_url(settings.database_url).startswith("sqlite")
        if is_pg:
            from sqlalchemy import text
            await conn.execute(text(
                "ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS audit_events_user_id_fkey"
            ))
        await conn.run_sync(Base.metadata.create_all)
