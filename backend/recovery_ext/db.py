from __future__ import annotations

import logging
from backend.db.session import engine
from backend.recovery_ext.models import ExtBase

logger = logging.getLogger(__name__)


async def init_ext_db() -> None:
    """Initialize extension database tables using CREATE TABLE IF NOT EXISTS."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(ExtBase.metadata.create_all)
        logger.info("Extension database tables initialized successfully.")
    except Exception as exc:
        logger.warning(f"Extension database table initialization failed: {exc}")
