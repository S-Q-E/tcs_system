from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.viewings import ZERO_UUID

DEFAULT_TZ = "America/New_York"
DEFAULT_DAYS = 14
DEFAULT_START_HOUR = 10
DEFAULT_END_HOUR = 17
DEFAULT_STEP_MINUTES = 60


def build_slot_starts(
    *,
    days: int = DEFAULT_DAYS,
    now: datetime | None = None,
    start_hour: int = DEFAULT_START_HOUR,
    end_hour: int = DEFAULT_END_HOUR,
    step_minutes: int = DEFAULT_STEP_MINUTES,
    tz_name: str = DEFAULT_TZ,
) -> list[datetime]:
    """Build UTC slot start timestamps for Mon-Fri [start_hour, end_hour) in tz_name.

    Skips weekends and timestamps <= now. Wall-clock times are converted via
    ZoneInfo so DST transitions (spring forward / fall back) keep local hours.
    """
    if days < 1:
        return []
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    tz = ZoneInfo(tz_name)
    today_local = now_utc.astimezone(tz).date()
    starts: list[datetime] = []
    for offset in range(days + 1):
        day = today_local + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        minutes = start_hour * 60
        end_minutes = end_hour * 60
        while minutes < end_minutes:
            hour, minute = divmod(minutes, 60)
            local_dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
            utc_dt = local_dt.astimezone(UTC)
            if utc_dt > now_utc:
                starts.append(utc_dt)
            minutes += step_minutes
    return starts


async def generate_slots(
    session: AsyncSession,
    *,
    days: int = DEFAULT_DAYS,
    unit_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    duration_min: int = DEFAULT_STEP_MINUTES,
    now: datetime | None = None,
    tz_name: str = DEFAULT_TZ,
) -> tuple[int, int]:
    """Idempotently generate open viewing slots for the next `days` days.

    Returns `(created_count, total_candidates)`. Does not commit.
    """
    starts = build_slot_starts(
        days=days,
        now=now,
        step_minutes=duration_min,
        tz_name=tz_name,
    )
    if not starts:
        return 0, 0
    result = await session.execute(
        text(
            "INSERT INTO tcs_crm_viewing_slots"
            " (starts_at, duration_min, unit_id, status, created_by)"
            " SELECT s, :duration_min, :unit_id, 'open', :created_by"
            " FROM unnest(CAST(:starts AS timestamptz[])) AS s"
            " ON CONFLICT (starts_at, COALESCE(unit_id, CAST(:zero_uuid AS uuid)))"
            " DO NOTHING"
            " RETURNING id"
        ),
        {
            "starts": starts,
            "duration_min": duration_min,
            "unit_id": unit_id,
            "created_by": created_by,
            "zero_uuid": ZERO_UUID,
        },
    )
    created = len(result.all())
    return created, len(starts)
