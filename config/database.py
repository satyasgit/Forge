"""
Database connection and session management.

Supports:
- PostgreSQL (production)
- SQLite (fallback for development if DATABASE_URL not set)

Uses SQLAlchemy 2.0+ async support for async operations.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from config.settings import settings

logger = logging.getLogger(__name__)

# Detect if we're using PostgreSQL or SQLite
is_postgres = settings.database_url.startswith("postgresql") if settings.database_url else False

# ── Sync Engine (for migrations, scripts) ─────────────────────────────────────

if is_postgres:
    # PostgreSQL
    engine = create_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Check connection health
        echo=settings.api_port == 8001,  # Log SQL in debug mode
    )
    logger.info("Database: PostgreSQL configured")
else:
    # SQLite fallback
    db_path = Path(settings.memory_db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    logger.info("Database: SQLite fallback at %s", db_path)

# ── Sync Session ─────────────────────────────────────────────────────────────

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Async Engine & Session (for FastAPI) ─────────────────────────────────────

if is_postgres:
    # Use asyncpg for PostgreSQL
    async_engine = create_async_engine(
        settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
        echo=False,
        pool_size=20,
        max_overflow=30,
    )
else:
    # SQLite async (aiosqlite)
    async_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )

AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

# ── Base ──────────────────────────────────────────────────────────────────────

Base = declarative_base()

# ── Dependency Injection ─────────────────────────────────────────────────────

def get_db() -> Session:
    """Dependency for sync DB operations (migrations, scripts)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for async DB operations (FastAPI)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Utility Functions ────────────────────────────────────────────────────────

async def init_db():
    """Create all tables (for development/testing only)."""
    try:
        # Import models to register them with Base
        import pipeline.models_database  # noqa: F401
        async with async_engine.begin() as conn:
            # In production, use Alembic migrations
            # For dev, we create all tables
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
    except ImportError as e:
        logger.error("Failed to import models: %s", e)
        raise


async def drop_db():
    """Drop all tables (for development only)."""
    from pipeline import models_database
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped")
