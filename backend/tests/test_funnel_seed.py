"""A fresh database gets exactly one pipeline with exactly six stages."""

from __future__ import annotations

import asyncio
import os
import uuid

import asyncpg
import pytest

from backend.tests.conftest import REPO_ROOT

pytestmark = pytest.mark.usefixtures("db_available")


def _dsn(settings) -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def test_fresh_db_has_one_six_stage_pipeline(settings):
    admin_dsn = _dsn(settings)
    db_name = f"crm_fresh_{uuid.uuid4().hex[:8]}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin.close()
    dsn = admin_dsn.rsplit("/", 1)[0] + "/" + db_name

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = dsn
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
        # A brand-new database has no bot tables at all; migrations must
        # still succeed (guarded tcs_* backfills).
        await asyncio.to_thread(command.upgrade, cfg, "head")

        conn = await asyncpg.connect(dsn)
        try:
            pipelines = await conn.fetch("SELECT name, is_default FROM crm_pipelines")
            stages = await conn.fetch(
                "SELECT name, color, kind, bot_stage_key, bot_status_key"
                " FROM crm_stages ORDER BY sort"
            )
            reasons = await conn.fetchval("SELECT COUNT(*) FROM crm_lost_reasons")
        finally:
            await conn.close()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            await admin.close()

    assert [row["name"] for row in pipelines] == ["TCS Leasing"]
    assert pipelines[0]["is_default"] is True
    assert len(stages) == 6
    assert [
        (row["name"], row["color"], row["kind"], row["bot_stage_key"], row["bot_status_key"])
        for row in stages
    ] == [
        ("New inquiry", "#38BDF8", "open", "NEW_INQUIRY", None),
        ("Qualified", "#818CF8", "open", "QUALIFIED", None),
        ("Viewing scheduled", "#FBBF24", "open", "VIEWING_SCHEDULED", None),
        ("Viewing done", "#34D399", "open", "VIEWING_DONE", None),
        ("Leased", "#16A34A", "won", None, "LEASED"),
        ("Lost", "#EF4444", "lost", None, "LOST"),
    ]
    assert reasons == 5
