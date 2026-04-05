#!/usr/bin/env python3
"""
Initialize PostgreSQL database for Phase 4.

Creates all tables defined in models_database.

Usage:
    python scripts/init_db.py

Environment:
    DATABASE_URL=postgresql://user:pass@localhost:5432/ai_agent_org
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.database import async_engine, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def main():
    try:
        logger.info("Initializing database...")
        await init_db()
        logger.info("✅ Database initialized successfully!")
    except Exception as e:
        logger.error("❌ Failed to initialize database: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
