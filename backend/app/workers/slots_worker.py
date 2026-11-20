from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..db import create_engine, create_session_factory
from ..services.slots import DEFAULT_DAYS, generate_slots

logger = logging.getLogger(__name__)

# Distinct from alembic (92030000), sync (92030001), notify (92030002), outbox (92030003).
SLOTS_LOCK_KEY = 92030004
SLOTS_INTERVAL_SECONDS = 24 * 60 * 60


async def run_slots_cycle(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    days: int = DEFAULT_DAYS,
) -> int | None:
    """Idempotently replenish the rolling viewing-slot window.

    Returns the number of newly created slots, or None when another instance
    holds the advisory lock.
    """
    async with session_factory() as session:
        got_lock = (
            await session.execute(
                text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": SLOTS_LOCK_KEY}
            )
        ).scalar()
        if not got_lock:
            logger.debug("slots replenish skipped: lock held by another instance")
            return None
        created, total = await generate_slots(session, days=days)
        await session.commit()
    logger.info("slots replenish done created=%d window_candidates=%d", created, total)
    return created


async def slots_loop(
    session_factory: async_sessionmaker[AsyncSession],
    interval_seconds: int = SLOTS_INTERVAL_SECONDS,
    days: int = DEFAULT_DAYS,
) -> None:
    """Daily background loop keeping a 14-day viewing slot window populated."""
    while True:
        try:
            await run_slots_cycle(session_factory, days=days)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("slots replenish cycle failed")
        await asyncio.sleep(interval_seconds)


async def _cli_main() -> int:
    settings = Settings()
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        created = await run_slots_cycle(factory)
        print(f"Slots replenish OK: created={created}")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_cli_main()))
