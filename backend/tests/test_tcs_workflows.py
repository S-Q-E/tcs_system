"""Static and DB-level checks for the generated TCS n8n workflows."""

from __future__ import annotations

import importlib.util
import json
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
    for forbidden in ("tcs_units", "viewing_bookings", "manager_handoffs"):
        assert forbidden not in text

    data = _workflow(BOT)
    nodes = {n["name"]: n for n in data["nodes"]}
    types = {n["type"] for n in data["nodes"]}
    assert "n8n-nodes-base.telegramTrigger" in types
    assert not any("googleSheets" in t or "vectorStore" in t for t in types)

    # All 4 tools are Postgres tools using `postgres demo` and attached to AI Agent.
    connections = data["connections"]["AI Agent"]
    tools = {t["node"] for t in connections["ai_tool"][0]}
    assert tools == {"search_units", "get_slots", "book_viewing", "handoff_to_human"}
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
    assert "LIMIT 3" in nodes["get_slots"]["parameters"]["query"]


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
    assert "America/New_York" in query
    assert "LIMIT 3" in query
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
