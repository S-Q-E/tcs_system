"""Static and DB-level checks for the generated TCS n8n workflows."""

from __future__ import annotations

import importlib.util
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parents[2]
SEND = ROOT / "docs" / "n8n" / "tcs-send-message-telegram.workflow.json"
BOT = ROOT / "workflows" / "tcs_bot.json"
REMINDERS = ROOT / "workflows" / "tcs_reminders.json"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_workflow", ROOT / "scripts" / "validate_workflow.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_generated_workflows_validate():
    validator = _load_validator()
    for path in (SEND, BOT, REMINDERS):
        assert path.exists(), path
        assert validator.validate(path) == [], path


def test_send_message_uses_telegram_send():
    data = _workflow(SEND)
    names = {n["name"] for n in data["nodes"]}
    types = {n["type"] for n in data["nodes"]}
    assert "Send Telegram Message" in names
    assert "n8n-nodes-base.telegram" in types
    node = next(n for n in data["nodes"] if n["name"] == "Send Telegram Message")
    assert node.get("onError") == "continueErrorOutput"
    # Telegram chat id = whatsapp_id without the tg: prefix.
    assert "replace(/^tg:/" in node["parameters"]["chatId"]


def test_bot_workflow_targets_tcs_tables_only():
    text = BOT.read_text(encoding="utf-8")
    assert "tcs_leads" in text and "tcs_messages" in text and "tcs_events" in text
    assert "tcs_crm_units" in text
    assert "tcs_crm_viewing_slots" in text
    assert "tcs_crm_book_viewing" in text
    assert "tcs_units" not in text
    for forbidden in ("viewing_bookings", "manager_handoffs"):
        assert re.search(rf"(?<!tcs_crm_){forbidden}", text) is None, forbidden

    data = _workflow(BOT)
    nodes = {n["name"]: n for n in data["nodes"]}
    types = {n["type"] for n in data["nodes"]}
    assert "n8n-nodes-base.telegramTrigger" in types
    assert not any("googleSheets" in t or "vectorStore" in t for t in types)

    # All 4 tools are Postgres tools using `postgres demo` and attached to AI Agent.
    connections = data["connections"]["AI Agent"]
    tools = {t["node"] for t in connections["ai_tool"][0]}
    assert tools == {
        "search_units",
        "get_slots",
        "book_viewing",
        "cancel_viewing",
        "handoff_to_human",
    }
    for tool_name in tools:
        assert nodes[tool_name]["type"] == "n8n-nodes-base.postgresTool"
        assert nodes[tool_name]["credentials"]["postgres"]["name"] == "postgres demo"

    # book_viewing and handoff_to_human take whatsapp_id from Normalize Message, never from model.
    assert (
        "$('Normalize Message').item.json.whatsapp_id"
        in nodes["book_viewing"]["parameters"]["options"]["queryReplacement"]
    )
    assert (
        "$('Normalize Message').item.json.whatsapp_id"
        in nodes["handoff_to_human"]["parameters"]["options"]["queryReplacement"]
    )
    assert "deleted_at IS NULL" in nodes["search_units"]["parameters"]["query"]
    assert "LIMIT LEAST(GREATEST(" in nodes["get_slots"]["parameters"]["query"]

    # Pet filter uses explicit flags, not free-text policy.
    search = nodes["search_units"]["parameters"]
    assert "allows_dogs" in search["query"] and "allows_cats" in search["query"]
    assert "$fromAI('pet_type'" in search["options"]["queryReplacement"]
    assert "pets_policy, '')) NOT LIKE 'no pets" not in search["query"]

    # Cancel tool takes whatsapp_id from Normalize Message and calls the DB function.
    cancel = nodes["cancel_viewing"]["parameters"]
    assert nodes["cancel_viewing"]["type"] == "n8n-nodes-base.postgresTool"
    assert "$('Normalize Message').item.json.whatsapp_id" in cancel["options"]["queryReplacement"]
    assert "LATERAL tcs_crm_cancel_viewing" in cancel["query"]
    assert "no_active_booking" in cancel["query"]


def test_bot_prompt_is_the_documented_prompt():
    prompt = (ROOT / "docs" / "tcs" / "bot-prompt.md").read_text(encoding="utf-8").rstrip()
    agent = next(n for n in _workflow(BOT)["nodes"] if n["name"] == "AI Agent")
    # The system prompt is systemMessage; `text` is the incoming user message.
    assert agent["parameters"]["text"] == "={{ $('Normalize Message').item.json.text }}"
    assert agent["parameters"]["options"]["systemMessage"].startswith("=" + prompt)
    assert "get_slots" in prompt
    assert "handoff_to_human" in prompt


def test_bot_prompt_handoff_guardrails():
    prompt = (ROOT / "docs" / "tcs" / "bot-prompt.md").read_text(encoding="utf-8")
    # Empty slots must be explained, never escalated.
    assert "empty list, do NOT hand off" in prompt
    assert "Monday-Friday, 10:00-17:00 ET" in prompt
    # Handoff only for an explicit request, a complaint, or two tool failures.
    assert "explicitly asks for a human" in prompt
    assert "complains" in prompt
    assert "two tool calls in a row failed" in prompt
    # A vague request asks one clarifying question instead of handing off.
    assert "ask ONE question" in prompt
    # The old unconditional handoff wording is gone.
    assert "offer to connect the person with a human manager via handoff_to_human" not in prompt
    assert "If you do not have the answer, say the team will follow up and call" not in prompt


def test_get_slots_supports_from_date():
    data = _workflow(BOT)
    slots = next(n for n in data["nodes"] if n["name"] == "get_slots")
    params = slots["parameters"]
    assert "$fromAI('from_date'" in params["options"]["queryReplacement"]
    query = params["query"]
    assert "from_date" in query
    assert "GREATEST(" in query
    assert "LIMIT LEAST(GREATEST(" in query
    assert "$fromAI('limit'" in params["options"]["queryReplacement"]
    assert "America/New_York" in query
    assert "LIMIT LEAST(GREATEST(" in query
    assert "is not a reason to hand off" in params["toolDescription"]
    assert "Monday-Friday 10:00-17:00 ET" in params["toolDescription"]

    handoff = next(n for n in data["nodes"] if n["name"] == "handoff_to_human")
    desc = handoff["parameters"]["toolDescription"]
    assert "ONLY" in desc
    assert "empty slot list" in desc


def test_bot_behavior_cases_are_documented():
    cases = (ROOT / "docs" / "tcs" / "bot-behavior-cases.md").read_text(encoding="utf-8")
    for phrase in (
        "Sunday, November 23",
        "I need an apartment",
        "Can I speak to a manager",
        "Show me viewings for next week",
        "returns an error once, then again",
    ):
        assert phrase in cases, phrase
    # Each case states what must not happen (handoff/no-handoff expectations).
    assert cases.count("| `handoff_to_human`") >= 1
    assert "| `handoff_to_human`;" in cases
    assert "Must NOT happen" in cases


def test_handoff_writes_one_event_and_stage_events_are_guarded():
    data = _workflow(BOT)
    nodes = {n["name"]: n for n in data["nodes"]}
    # The tool must not write its own event; Validate & Normalize does it once.
    assert "INSERT INTO tcs_events" not in nodes["handoff_to_human"]["parameters"]["query"]
    js = nodes["Validate & Normalize Agent Output"]["parameters"]["jsCode"]
    assert js.count("'transferred_to_manager'") == 1
    # Stage events use the effective stage (SQL guard mirrored in JS).
    assert "effectiveStage" in js
    assert "effectiveStage !== lead.current_stage" in js
    # Empty/zero collected values are dropped instead of overwriting lead_data.
    assert "typeof value === 'string'" in js
    assert "value === 0" in js
    # Agent context exposes today's weekday/date in ET.
    ctx = nodes["Build Agent Context"]["parameters"]["jsCode"]
    assert "today_et" in ctx and "America/New_York" in ctx


def test_prompt_has_budget_and_cancel_rules():
    prompt = (ROOT / "docs" / "tcs" / "bot-prompt.md").read_text(encoding="utf-8")
    assert "Budget rule" in prompt
    assert "never substitute your own number" in prompt
    assert "cancel_viewing" in prompt
    assert "only when it returns result = 'cancelled'" in prompt
    assert "Do not ask why" in prompt
    assert "limit=8" in prompt
    assert "Today is {{ $('Build Agent Context').item.json.today_et }}" in prompt


def test_pet_flags_helper():
    from backend.app.routers.units import _pet_flags

    assert _pet_flags("Only cats") == (False, True)
    assert _pet_flags("Cats only") == (False, True)
    assert _pet_flags("Cats and small dogs allowed") == (True, True)
    assert _pet_flags("No pets") == (False, False)
    assert _pet_flags(None) == (False, False)


def test_reminders_every_15_minutes():
    trigger = next(
        n for n in _workflow(REMINDERS)["nodes"] if n["type"] == "n8n-nodes-base.scheduleTrigger"
    )
    interval = trigger["parameters"]["rule"]["interval"][0]
    assert interval == {"field": "minutes", "minutesInterval": 15}
    text = REMINDERS.read_text(encoding="utf-8")
    assert "reminder_sent = true" in text
    assert "interval '24 hours'" in text
    assert "tcs_crm_units" in text
    assert "tcs_units" not in text
    # Empty results must not reach Telegram: a guard node sits before Send Reminder.
    data = _workflow(REMINDERS)
    names = [n["name"] for n in data["nodes"]]
    assert "Has Reminders?" in names
    assert "Has Reminders?" in data["connections"]
    assert data["connections"]["Find Upcoming Viewings"]["main"][0][0]["node"] == "Has Reminders?"


@pytest.mark.usefixtures("db_available", "migrated")
async def test_update_lead_state_does_not_downgrade_booked_viewing(settings):
    """Update Lead State SQL must not downgrade stage/status/reminder_sent
    when a lead already has VIEWING_SCHEDULED and a future trial_datetime.
    """
    data = _workflow(BOT)
    node = next(n for n in data["nodes"] if n["name"] == "Update Lead State")
    sql = node["parameters"]["query"]

    dsn = settings.dsn
    conn = await asyncpg.connect(dsn=dsn)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            wa = f"tg:guard_{uuid.uuid4().hex[:8]}"
            future = datetime.now(UTC) + timedelta(days=2)
            await conn.execute(
                "INSERT INTO tcs_leads"
                " (whatsapp_id, name, current_stage, previous_stage, status,"
                " trial_datetime, reminder_sent)"
                " VALUES ($1, 'Guard Lead', 'VIEWING_SCHEDULED', 'QUALIFIED',"
                " 'VIEWING_BOOKED', $2, true)",
                wa,
                future,
            )

            # Model tries to downgrade to QUALIFIED / ACTIVE
            await conn.execute(
                sql,
                wa,
                "QUALIFIED",
                "NEW_INQUIRY",
                "ACTIVE",
                "{}",
                "",
                "",
                "",
                "",
                "",
                "0.8",
            )
            row = await conn.fetchrow(
                "SELECT current_stage, previous_stage, status, reminder_sent"
                " FROM tcs_leads WHERE whatsapp_id = $1",
                wa,
            )
            assert row["current_stage"] == "VIEWING_SCHEDULED"
            assert row["previous_stage"] == "QUALIFIED"
            assert row["status"] == "VIEWING_BOOKED"
            assert row["reminder_sent"] is True

            # Model advancing to HANDOFF status is still permitted
            await conn.execute(
                sql,
                wa,
                "QUALIFIED",
                "VIEWING_SCHEDULED",
                "HANDOFF",
                "{}",
                "",
                "",
                "",
                "",
                "",
                "0.9",
            )
            row2 = await conn.fetchrow(
                "SELECT current_stage, status, reminder_sent"
                " FROM tcs_leads WHERE whatsapp_id = $1",
                wa,
            )
            assert row2["current_stage"] == "VIEWING_SCHEDULED"
            assert row2["status"] == "HANDOFF"
            assert row2["reminder_sent"] is True

            # Model advancing to VIEWING_DONE is still permitted
            await conn.execute(
                sql,
                wa,
                "VIEWING_DONE",
                "VIEWING_SCHEDULED",
                "ACTIVE",
                "{}",
                "",
                "",
                "",
                "",
                "",
                "0.9",
            )
            row3 = await conn.fetchrow(
                "SELECT current_stage FROM tcs_leads WHERE whatsapp_id = $1", wa
            )
            assert row3["current_stage"] == "VIEWING_DONE"
        finally:
            await tx.rollback()
    finally:
        await conn.close()


@pytest.mark.usefixtures("db_available", "migrated")
async def test_update_lead_state_keeps_known_lead_data(settings):
    """An empty/zero collected value must not wipe a known unit or budget."""
    data = _workflow(BOT)
    nodes = {n["name"]: n for n in data["nodes"]}
    sql = nodes["Update Lead State"]["parameters"]["query"]

    conn = await asyncpg.connect(dsn=settings.dsn)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            wa = f"tg:ld_{uuid.uuid4().hex[:8]}"
            await conn.execute(
                "INSERT INTO tcs_leads (whatsapp_id, name, current_stage, status, lead_data)"
                " VALUES ($1, 'LD Lead', 'QUALIFIED', 'ACTIVE', $2::jsonb)",
                wa,
                '{"unit": "Demo Residences A A-101", "budget_usd": 1500}',
            )
            await conn.execute(
                sql,
                wa,
                "QUALIFIED",
                "QUALIFIED",
                "ACTIVE",
                '{"unit": "", "budget_usd": 0, "pets": "dog"}',
                "",
                "",
                "",
                "",
                "",
                "0.7",
            )
            row = await conn.fetchrow("SELECT lead_data FROM tcs_leads WHERE whatsapp_id = $1", wa)
            lead_data = json.loads(row["lead_data"])
            assert lead_data["unit"] == "Demo Residences A A-101"
            assert lead_data["budget_usd"] == 1500
            assert lead_data["pets"] == "dog"
        finally:
            await tx.rollback()
    finally:
        await conn.close()


@pytest.mark.usefixtures("db_available", "migrated")
async def test_booking_keeps_unit_and_reminder_shows_address(settings):
    """After book_viewing the lead keeps the unit label and the reminder has the address."""
    bot = {n["name"]: n for n in _workflow(BOT)["nodes"]}
    reminders = {n["name"]: n for n in _workflow(REMINDERS)["nodes"]}
    update_sql = bot["Update Lead State"]["parameters"]["query"]
    reminder_sql = reminders["Find Upcoming Viewings"]["parameters"]["query"]

    conn = await asyncpg.connect(dsn=settings.dsn)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            wa = f"tg:addr_{uuid.uuid4().hex[:8]}"
            await conn.execute(
                "INSERT INTO tcs_leads (whatsapp_id, name, current_stage, status)"
                " VALUES ($1, 'Addr Lead', 'QUALIFIED', 'ACTIVE')",
                wa,
            )
            unit_id = await conn.fetchval(
                "INSERT INTO tcs_crm_units"
                " (building, unit_number, beds, baths, rent_usd, status,"
                "  allows_dogs, allows_cats)"
                " VALUES ('Test Residences Z', 'Z-1', 1, 1, 1500, 'available',"
                "         true, true) RETURNING id"
            )
            slot_id = await conn.fetchval(
                "INSERT INTO tcs_crm_viewing_slots (starts_at, duration_min, status, unit_id)"
                " VALUES (now() + interval '3 hours', 60, 'open', $1) RETURNING id",
                unit_id,
            )
            await conn.execute(
                "SELECT tcs_crm_book_viewing($1, $2, $3, 'Addr Lead')", wa, slot_id, unit_id
            )

            # The model later sends an empty unit (e.g. a vague follow-up).
            await conn.execute(
                update_sql,
                wa,
                "VIEWING_SCHEDULED",
                "QUALIFIED",
                "VIEWING_BOOKED",
                '{"unit": "", "budget_usd": 0}',
                "",
                "",
                "",
                "",
                "",
                "0.8",
            )
            lead = await conn.fetchrow(
                "SELECT lead_data, trial_datetime FROM tcs_leads WHERE whatsapp_id = $1", wa
            )
            assert json.loads(lead["lead_data"])["unit"] == "Test Residences Z Z-1"

            rows = await conn.fetch(reminder_sql)
            match = [r for r in rows if r["whatsapp_id"] == wa]
            assert match, "reminder query returned no row for the booked lead"
            assert match[0]["building"] == "Test Residences Z"
            assert match[0]["unit_number"] == "Z-1"
            assert "Test Residences Z, Unit Z-1" in match[0]["reminder_text"]
        finally:
            await tx.rollback()
    finally:
        await conn.close()


@pytest.mark.usefixtures("db_available", "migrated")
async def test_search_units_pet_type_excludes_cats_only(settings):
    """pet_type='dog' must not return a cats-only unit."""
    bot = {n["name"]: n for n in _workflow(BOT)["nodes"]}
    sql = bot["search_units"]["parameters"]["query"]

    conn = await asyncpg.connect(dsn=settings.dsn)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            suffix = uuid.uuid4().hex[:6]
            cats_only = await conn.fetchval(
                "INSERT INTO tcs_crm_units"
                " (building, unit_number, beds, baths, rent_usd, pets_policy,"
                "  allows_dogs, allows_cats, status)"
                " VALUES ($1, 'C-1', 1, 1, 1000, 'Only cats', false, true, 'available')"
                " RETURNING id",
                f"Cats Only {suffix}",
            )
            both = await conn.fetchval(
                "INSERT INTO tcs_crm_units"
                " (building, unit_number, beds, baths, rent_usd, pets_policy,"
                "  allows_dogs, allows_cats, status)"
                " VALUES ($1, 'D-1', 1, 1, 1100, 'Cats and small dogs allowed',"
                "         true, true, 'available') RETURNING id",
                f"Dogs Ok {suffix}",
            )
            dogs = await conn.fetch(sql, None, None, "dog")
            dog_ids = {r["unit_id"] for r in dogs}
            assert both in dog_ids
            assert cats_only not in dog_ids

            cats = await conn.fetch(sql, None, None, "cat")
            cat_ids = {r["unit_id"] for r in cats}
            assert {cats_only, both} <= cat_ids

            none = await conn.fetch(sql, None, None, "none")
            none_ids = {r["unit_id"] for r in none}
            assert {cats_only, both} <= none_ids
        finally:
            await tx.rollback()
    finally:
        await conn.close()


@pytest.mark.usefixtures("db_available", "migrated")
async def test_update_lead_state_does_not_restore_stage_without_trial(settings):
    """After a cancel (trial_datetime is NULL) the model's VIEWING_SCHEDULED
    output must not put the lead back into a booked-viewing state.
    """
    data = _workflow(BOT)
    nodes = {n["name"]: n for n in data["nodes"]}
    sql = nodes["Update Lead State"]["parameters"]["query"]

    conn = await asyncpg.connect(dsn=settings.dsn)
    try:
        tx = conn.transaction()
        await tx.start()
        try:
            wa = f"tg:notrial_{uuid.uuid4().hex[:8]}"
            await conn.execute(
                "INSERT INTO tcs_leads (whatsapp_id, name, current_stage, status, lead_data)"
                " VALUES ($1, 'No Trial', 'QUALIFIED', 'ACTIVE', '{}'::jsonb)",
                wa,
            )
            await conn.execute(
                sql,
                wa,
                "VIEWING_SCHEDULED",
                "VIEWING_SCHEDULED",
                "VIEWING_BOOKED",
                "{}",
                "",
                "",
                "",
                "",
                "",
                "0.8",
            )
            row = await conn.fetchrow(
                "SELECT current_stage, status, trial_datetime"
                " FROM tcs_leads WHERE whatsapp_id = $1",
                wa,
            )
            assert row["current_stage"] == "QUALIFIED"
            assert row["status"] == "ACTIVE"
            assert row["trial_datetime"] is None
        finally:
            await tx.rollback()
    finally:
        await conn.close()
