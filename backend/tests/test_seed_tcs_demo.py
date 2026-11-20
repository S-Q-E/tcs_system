"""Tests for scripts/seed_tcs_demo.py (protection, idempotency, --reset).

All database work runs inside a rolled-back transaction, so the tests never
leave demo rows behind. The TCS pipeline itself is seeded by Alembic.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest

from backend.tests.conftest import REPO_ROOT

pytestmark = pytest.mark.usefixtures("migrated")

_SCRIPT = REPO_ROOT / "scripts" / "seed_tcs_demo.py"
_spec = importlib.util.spec_from_file_location("seed_tcs_demo", _SCRIPT)
assert _spec and _spec.loader
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def _dsn(settings) -> str:
    url = settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture()
async def conn(settings, db_available):
    connection = await asyncpg.connect(dsn=_dsn(settings))
    try:
        tx = connection.transaction()
        await tx.start()
        try:
            # The shared test DB contains fixture rows with source='telegram';
            # wipe the bot slice inside the transaction (rolled back later).
            for table in ("tcs_messages", "tcs_events", "tcs_followups", "tcs_ai_metrics"):
                await connection.execute(f"DELETE FROM {table}")
            await connection.execute("DELETE FROM tcs_leads")
            yield connection
        finally:
            await tx.rollback()  # never leave demo rows behind
    finally:
        await connection.close()


async def test_confirm_refuses_without_env():
    assert seed.confirm_error({}) is not None
    assert seed.confirm_error({seed.CONFIRM_ENV: seed.CONFIRM_VALUE}) is None


async def test_schema_check_blocks_telegram_rows(conn):
    await conn.execute(
        "INSERT INTO tcs_leads (whatsapp_id, source)"
        " VALUES ($1, 'telegram') ON CONFLICT DO NOTHING",
        "tg:111111111",
    )
    error = await seed.schema_error(conn)
    assert error is not None and "Refusing to run" in error

    await conn.execute("DELETE FROM tcs_leads WHERE whatsapp_id = 'tg:111111111'")
    assert await seed.schema_error(conn) is None


async def test_pipeline_must_exist_and_match(conn):
    assert await seed.pipeline_error(conn) is None

    # The script never creates or renames pipeline rows; a missing or
    # different pipeline is an error.
    await conn.execute(
        "UPDATE tcs_crm_pipelines SET name = 'Renamed' WHERE name = $1", seed.PIPELINE_NAME
    )
    error = await seed.pipeline_error(conn)
    assert error is not None and "not found" in error


async def test_seed_idempotent_and_complete(conn):
    await seed.schema_error(conn)
    first = await seed.run_seed(conn)
    second = await seed.run_seed(conn)

    assert first == second
    assert first["leads"] == 30
    assert first["units"] == 14
    assert first["slots"] > 0

    crm_units = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_crm_units WHERE deleted_at IS NULL"
    )
    assert crm_units >= 14
    crm_slots = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_crm_viewing_slots WHERE starts_at > now()"
    )
    assert crm_slots >= first["slots"]
    for legacy in ("tcs_units", "viewing_bookings", "manager_handoffs"):
        assert await conn.fetchval("SELECT to_regclass($1)", legacy) is None

    # The pipeline is the only one and has exactly six stages (from Alembic).
    pipelines = await conn.fetch("SELECT name, is_default FROM tcs_crm_pipelines ORDER BY name")
    assert [row["name"] for row in pipelines] == ["TCS Leasing"]
    assert pipelines[0]["is_default"] is True
    stages = await conn.fetch(
        "SELECT name, kind, bot_stage_key, bot_status_key FROM tcs_crm_stages"
        " WHERE pipeline_id = (SELECT id FROM tcs_crm_pipelines WHERE name = 'TCS Leasing')"
        " ORDER BY sort"
    )
    assert [row["name"] for row in stages] == [
        "New inquiry",
        "Qualified",
        "Viewing scheduled",
        "Viewing done",
        "Leased",
        "Lost",
    ]
    won = next(row for row in stages if row["name"] == "Leased")
    assert won["bot_status_key"] == "LEASED"
    lost = next(row for row in stages if row["name"] == "Lost")
    assert lost["bot_status_key"] == "LOST"

    # unanswered_after_minutes is a JSON number 2.
    raw = await conn.fetchval(
        "SELECT value FROM tcs_crm_settings WHERE key = 'unanswered_after_minutes'"
    )
    value = json.loads(raw) if isinstance(raw, str) else raw
    assert value == 2

    # Exactly one unanswered dialog: NEW_INQUIRY, last message 'in' ~30 min ago.
    last_directions = await conn.fetch(
        """
        SELECT DISTINCT ON (l.whatsapp_id) l.whatsapp_id, m.direction
        FROM tcs_leads l
        JOIN tcs_messages m ON m.whatsapp_id = l.whatsapp_id
        WHERE l.source = 'demo'
        ORDER BY l.whatsapp_id, m.created_at DESC, m.id DESC
        """
    )
    incoming = [row["whatsapp_id"] for row in last_directions if row["direction"] == "in"]
    assert incoming == ["tg:900000000"]
    unanswered_stage = await conn.fetchval(
        "SELECT current_stage FROM tcs_leads WHERE whatsapp_id = 'tg:900000000'"
    )
    assert unanswered_stage == "NEW_INQUIRY"

    last_in = await conn.fetchval(
        """
        SELECT m.created_at FROM tcs_leads l
        JOIN tcs_messages m ON m.whatsapp_id = l.whatsapp_id
        WHERE l.source = 'demo' AND l.whatsapp_id = 'tg:900000000'
        ORDER BY m.created_at DESC LIMIT 1
        """
    )
    age_minutes = (datetime.now(UTC) - last_in).total_seconds() / 60
    assert 25 <= age_minutes <= 40, age_minutes

    # 4 / 6 / 4 / 8 / 3 / 5 leads per stage.
    per_stage = await conn.fetch(
        "SELECT current_stage, COUNT(*) AS n FROM tcs_leads WHERE source = 'demo'"
        " GROUP BY current_stage"
    )
    assert {row["current_stage"]: row["n"] for row in per_stage} == {
        "NEW_INQUIRY": 4,
        "QUALIFIED": 6,
        "VIEWING_SCHEDULED": 4,
        "VIEWING_DONE": 8,
        "LEASED": 3,
        "LOST": 5,
    }

    # Viewings: 4 upcoming, 8 done, 3 missed/cancelled back in Qualified,
    # and 3 leased after their viewing.
    trials = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_leads WHERE source = 'demo' AND trial_datetime IS NOT NULL"
    )
    assert trials == 18
    future = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_leads WHERE source = 'demo' AND trial_datetime > now()"
    )
    assert future == 4

    # Statuses: two handoffs, three leased, five lost.
    statuses = await conn.fetch(
        "SELECT status, COUNT(*) AS n FROM tcs_leads WHERE source = 'demo' GROUP BY status"
    )
    by_status = {row["status"]: row["n"] for row in statuses}
    assert by_status.get("HANDOFF") == 2
    assert by_status.get("LEASED") == 3
    assert by_status.get("LOST") == 5

    # After-hours share is 12 of 30 (Mon-Fri 09:00-17:00 ET).
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (l.whatsapp_id) m.created_at AS first_at
        FROM tcs_leads l
        JOIN tcs_messages m ON m.whatsapp_id = l.whatsapp_id
        WHERE l.source = 'demo'
        ORDER BY l.whatsapp_id, m.created_at ASC, m.id ASC
        """
    )
    after_hours = sum(
        1
        for row in rows
        if row["first_at"].astimezone(et).weekday() >= 5
        or not 9 <= row["first_at"].astimezone(et).hour < 17
    )
    assert after_hours == 12


async def test_reset_only_deletes_demo_rows(conn):
    await seed.schema_error(conn)
    await seed.run_seed(conn)

    # Foreign (non-demo) rows must survive --reset.
    await conn.execute(
        "INSERT INTO tcs_leads (whatsapp_id, source)"
        " VALUES ($1, 'telegram') ON CONFLICT DO NOTHING",
        "tg:999999999",
    )
    await conn.execute(
        "INSERT INTO tcs_messages (whatsapp_id, direction, content) VALUES ($1, 'in', 'real')",
        "tg:999999999",
    )
    await conn.execute(
        "INSERT INTO tcs_events (whatsapp_id, event_type) VALUES ($1, 'stage_entered')",
        "tg:999999999",
    )

    removed = await seed.seed_reset(conn)
    assert removed == 30

    demo_left = await conn.fetchval("SELECT COUNT(*) FROM tcs_leads WHERE source = 'demo'")
    assert demo_left == 0
    demo_msgs = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_messages"
        " WHERE whatsapp_id IN (SELECT whatsapp_id FROM tcs_leads WHERE source = 'demo')"
    )
    assert demo_msgs == 0

    foreign = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_leads WHERE whatsapp_id = 'tg:999999999'"
    )
    assert foreign == 1
    foreign_msgs = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_messages WHERE whatsapp_id = 'tg:999999999'"
    )
    assert foreign_msgs == 1
    foreign_events = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_events WHERE whatsapp_id = 'tg:999999999'"
    )
    assert foreign_events == 1


async def test_no_truncate_and_demo_marker(conn):
    """Demo rows are tagged with source='demo' (hard rule)."""
    await seed.schema_error(conn)
    await seed.run_seed(conn)
    sources = await conn.fetch(
        "SELECT DISTINCT source FROM tcs_leads WHERE whatsapp_id LIKE 'tg:900%'"
    )
    assert {row["source"] for row in sources} == {"demo"}
    row = await conn.fetchrow("SELECT lead_data FROM tcs_leads WHERE source = 'demo' LIMIT 1")
    data = row["lead_data"] if isinstance(row["lead_data"], dict) else json.loads(row["lead_data"])
    assert set(data) == {"budget_usd", "unit", "pets"}
    source = Path(seed.__file__).read_text(encoding="utf-8")
    assert "TRUNCATE TABLE" not in source
    raw = await conn.fetchval(
        "SELECT value::text FROM tcs_crm_settings WHERE key = 'unanswered_after_minutes'"
    )
    assert raw == "2"
    assert await conn.fetchval("SELECT 1") == 1  # connection still usable
