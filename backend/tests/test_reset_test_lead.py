"""Checks for scripts/reset_test_lead.py (test lead reset procedure)."""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "reset_test_lead", ROOT / "scripts" / "reset_test_lead.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reset_requires_demo_confirmation():
    module = _load_script()
    assert module.confirm_error({}) is not None
    assert module.confirm_error({"DEMO_DB_CONFIRM": "nope"}) is not None
    assert module.confirm_error({"DEMO_DB_CONFIRM": "I_UNDERSTAND_THIS_IS_A_DEMO_DB"}) is None


def test_reset_clears_chat_memory_and_keeps_audit_tables():
    src = (ROOT / "scripts" / "reset_test_lead.py").read_text(encoding="utf-8")
    assert "DELETE FROM n8n_chat_histories" in src
    assert "tcs_crm_cancel_viewing" in src
    assert "tcs_messages" not in src
    assert "tcs_events" not in src


@pytest.mark.usefixtures("db_available", "migrated")
async def test_reset_lead_cancels_booking_and_clears_memory(settings):
    module = _load_script()
    conn = await asyncpg.connect(dsn=settings.dsn)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            wa = f"tg:reset_{uuid.uuid4().hex[:8]}"
            await conn.execute(
                "INSERT INTO tcs_leads"
                " (whatsapp_id, name, current_stage, status, trial_datetime, lead_data)"
                " VALUES ($1, 'Reset Lead', 'VIEWING_SCHEDULED', 'VIEWING_BOOKED',"
                " $2, $3::jsonb)",
                wa,
                datetime.now(UTC) + timedelta(hours=2),
                json.dumps({"unit": "Demo Residences A A-101", "budget_usd": 1500}),
            )
            await conn.execute(
                "INSERT INTO tcs_crm_conversation_state (whatsapp_id, bot_paused)"
                " VALUES ($1, true)",
                wa,
            )
            unit_id = await conn.fetchval(
                "INSERT INTO tcs_crm_units"
                " (building, unit_number, beds, baths, rent_usd, status,"
                "  allows_dogs, allows_cats)"
                " VALUES ('Reset Residences', 'R-1', 1, 1, 1400, 'available',"
                "         true, true) RETURNING id"
            )
            slot_id = await conn.fetchval(
                "INSERT INTO tcs_crm_viewing_slots (starts_at, duration_min, status, unit_id)"
                " VALUES (now() + interval '2 hours', 60, 'open', $1) RETURNING id",
                unit_id,
            )
            await conn.execute(
                "SELECT tcs_crm_book_viewing($1, $2, $3, 'Reset Lead')", wa, slot_id, unit_id
            )
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS n8n_chat_histories"
                " (id serial PRIMARY KEY, session_id text NOT NULL, message jsonb NOT NULL)"
            )
            await conn.execute(
                "INSERT INTO n8n_chat_histories (session_id, message)"
                ' VALUES ($1, \'{"type": "human", "content": "hi"}\'::jsonb)',
                wa,
            )

            summary = await module.reset_lead(conn, wa)

            assert summary["cancelled_bookings"] == ["cancelled"]
            assert summary["chat_rows_deleted"] == 1
            lead = await conn.fetchrow(
                "SELECT status, current_stage, previous_stage, trial_datetime,"
                " lead_data, reminder_sent FROM tcs_leads WHERE whatsapp_id = $1",
                wa,
            )
            assert lead["status"] == "ACTIVE"
            assert lead["current_stage"] == "NEW_INQUIRY"
            assert lead["previous_stage"] is None
            assert lead["trial_datetime"] is None
            assert lead["reminder_sent"] is False
            assert json.loads(lead["lead_data"]) == {}
            state = await conn.fetchrow(
                "SELECT bot_paused FROM tcs_crm_conversation_state WHERE whatsapp_id = $1",
                wa,
            )
            assert state["bot_paused"] is False
            slot = await conn.fetchrow(
                "SELECT status FROM tcs_crm_viewing_slots WHERE id = $1", slot_id
            )
            assert slot["status"] == "open"
            booking = await conn.fetchrow(
                "SELECT status FROM tcs_crm_viewing_bookings WHERE whatsapp_id = $1", wa
            )
            assert booking["status"] == "cancelled"
        finally:
            await tx.rollback()
    finally:
        await conn.close()
