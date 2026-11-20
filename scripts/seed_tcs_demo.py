"""Seed the demo DB with fictional TCS leasing data.

The pipeline itself is created by Alembic (`funnel_seed.py`); this script only
checks that «TCS Leasing» with its six stages exists and fills the demo slice.

Safety:
- refuses to run unless DEMO_DB_CONFIRM=I_UNDERSTAND_THIS_IS_A_DEMO_DB;
- refuses to run when tcs_leads already has rows with source = 'telegram'
  (that looks like a production bot DB);
- ``--reset`` deletes ONLY rows whose source is 'demo' (and their messages,
  events, followups and metrics). Never TRUNCATE.

Run:  python scripts/seed_tcs_demo.py [--reset]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_SQL = ROOT / "tests" / "fixtures" / "tcs_schema.sql"

CONFIRM_ENV = "DEMO_DB_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_IS_A_DEMO_DB"
DEMO_SOURCE = "demo"
BLOCKING_SOURCE = "telegram"

ET = ZoneInfo("America/New_York")

PIPELINE_NAME = "TCS Leasing"

# The six stages the CRM seeds on an empty database. The script verifies them
# and never creates or renames pipeline rows.
EXPECTED_STAGES: tuple[tuple[str, str, str | None, str | None], ...] = (
    ("New inquiry", "open", "NEW_INQUIRY", None),
    ("Qualified", "open", "QUALIFIED", None),
    ("Viewing scheduled", "open", "VIEWING_SCHEDULED", None),
    ("Viewing done", "open", "VIEWING_DONE", None),
    ("Leased", "won", None, "LEASED"),
    ("Lost", "lost", None, "LOST"),
)

# ---------------------------------------------------------------- demo data

BUILDINGS = ("Demo Residences A", "Demo Residences B", "Demo Residences C")
UNITS_PER_BUILDING = (5, 5, 4)
PET_POLICIES = ("Cats and small dogs allowed", "No pets", "Cats only")
PREFERRED_TIMES = ("Weekday evenings", "Weekend afternoons", "Weekday mornings")
THINKING_OBJECTIONS = ("Price is a bit high", "Still comparing options")

FIRST_NAMES = (
    "Jordan",
    "Taylor",
    "Casey",
    "Riley",
    "Morgan",
    "Avery",
    "Quinn",
    "Skyler",
    "Aubrey",
    "Dakota",
    "Reese",
    "Rowan",
    "Emerson",
    "Finley",
    "Harper",
    "Sawyer",
    "Peyton",
    "Blake",
    "Devin",
    "Elliot",
    "Frankie",
    "Gray",
    "Hayden",
    "Jamie",
    "Kendall",
    "Lane",
    "Marley",
    "Noel",
    "Parker",
    "Shawn",
)

# (bot_stage_key, lead status, count) - exactly 30 leads.
STAGE_PLAN: tuple[tuple[str, str, int], ...] = (
    ("NEW_INQUIRY", "ACTIVE", 3),
    ("NEW_INQUIRY", "THINKING", 1),
    ("QUALIFIED", "ACTIVE", 2),
    ("QUALIFIED", "THINKING", 3),  # two no-shows and one cancellation
    ("QUALIFIED", "HANDOFF", 1),
    ("VIEWING_SCHEDULED", "VIEWING_BOOKED", 4),  # future viewings
    ("VIEWING_DONE", "ACTIVE", 6),
    ("VIEWING_DONE", "THINKING", 1),
    ("VIEWING_DONE", "HANDOFF", 1),
    ("LEASED", "LEASED", 3),
    ("LOST", "LOST", 5),
)
TOTAL_LEADS = 30
AFTER_HOURS_TARGET = 12  # of 30 first messages outside Mon-Fri 09:00-17:00 ET

IN_CONTENT = (
    "Hi, any 2-bedroom under $2,200?",
    "Do you have anything available for March?",
    "Is parking included with the units?",
    "What is the deposit on the 1BR?",
    "Can I visit the building this week?",
    "Do you accept pets? I have a cat.",
    "Hi, moving to Philly for work next month.",
    "How much is the 2BR at Demo Residences A?",
)
OUT_CONTENT = (
    "Hi! This is the TCS assistant. I can check availability right away.",
    "Sure - do you know the area you want and your move-in date?",
    "Yes, that unit is available. Would you like to schedule a viewing?",
    "Great, I can offer a few viewing slots this week.",
    "You are booked! I will send a reminder before the viewing.",
    "Our team will follow up shortly with the details.",
)


def _dsn() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://tcs:tcs@localhost:5432/tcs")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def confirm_error(env: dict[str, str] | None = None) -> str | None:
    """Return an error string when the demo confirmation env is missing."""
    env = os.environ if env is None else env
    if env.get(CONFIRM_ENV) != CONFIRM_VALUE:
        return (
            f"Refusing to run: set {CONFIRM_ENV}={CONFIRM_VALUE} "
            "to confirm this is a demo database."
        )
    return None


async def schema_error(conn: asyncpg.Connection) -> str | None:
    """Apply the bot schema when missing; refuse on real bot data."""
    if await conn.fetchval("SELECT to_regclass('tcs_leads')") is None:
        await conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        return None
    blocking = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_leads WHERE source = $1", BLOCKING_SOURCE
    )
    if blocking:
        return (
            f"Refusing to run: tcs_leads already has {blocking} row(s) with "
            f"source = '{BLOCKING_SOURCE}' (this does not look like a demo DB)."
        )
    return None


async def pipeline_error(conn: asyncpg.Connection) -> str | None:
    """The pipeline must already exist (Alembic seeds it). Never create it here."""
    row = await conn.fetchrow("SELECT id FROM tcs_crm_pipelines WHERE name = $1", PIPELINE_NAME)
    if row is None:
        return (
            f"Pipeline '{PIPELINE_NAME}' not found. Run "
            "`alembic upgrade head` first; this script never creates a pipeline."
        )
    stages = await conn.fetch(
        "SELECT name, kind, bot_stage_key, bot_status_key FROM tcs_crm_stages"
        " WHERE pipeline_id = $1 ORDER BY sort",
        row["id"],
    )
    actual = [(s["name"], s["kind"], s["bot_stage_key"], s["bot_status_key"]) for s in stages]
    if actual != list(EXPECTED_STAGES):
        return f"Pipeline '{PIPELINE_NAME}' does not match the expected six stages: " f"{actual!r}"
    return None


async def seed_units(conn: asyncpg.Connection) -> int:
    """Create tcs_units (idempotent) and insert 14 demo units (2 leased)."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tcs_units (
            id SERIAL PRIMARY KEY,
            building TEXT,
            unit_number TEXT,
            beds INT,
            baths NUMERIC,
            rent_usd INT,
            deposit_usd INT,
            available_from DATE,
            status TEXT DEFAULT 'available',
            pets_policy TEXT,
            description TEXT,
            UNIQUE (building, unit_number)
        )
        """
    )
    now = datetime.now(ET).date()
    rows: list[tuple] = []
    unit_index = 0
    leased_planned = 0
    for building, count in zip(BUILDINGS, UNITS_PER_BUILDING, strict=True):
        for i in range(1, count + 1):
            unit_index += 1
            beds = 1 + unit_index % 3
            baths = 1 if beds == 1 else 2
            rent = 1300 + beds * 300 + i * 25
            deposit = rent
            available = now + timedelta(days=unit_index % 20)
            status = "available"
            # Two leased units, deterministic: A-2 and B-3.
            if leased_planned < 2 and building.endswith("A") and i == 2:
                status = "leased"
                leased_planned += 1
            elif leased_planned < 2 and building.endswith("B") and i == 3:
                status = "leased"
                leased_planned += 1
            pets = PET_POLICIES[unit_index % len(PET_POLICIES)]
            description = (
                f"{beds}BR/{baths}BA demo unit with {pets.lower()}. "
                "Fictional listing for the TCS demo."
            )
            rows.append(
                (
                    building,
                    f"{building[-1]}-{100 + i}",
                    beds,
                    baths,
                    rent,
                    deposit,
                    available,
                    status,
                    pets,
                    description,
                )
            )
    await conn.executemany(
        """
        INSERT INTO tcs_units (
            building, unit_number, beds, baths, rent_usd, deposit_usd,
            available_from, status, pets_policy, description
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (building, unit_number) DO NOTHING
        """,
        rows,
    )
    return len(rows)


async def seed_settings(conn: asyncpg.Connection) -> None:
    """unanswered_after_minutes = 2 (JSON number)."""
    await conn.execute(
        "INSERT INTO tcs_crm_settings (key, value)"
        " VALUES ('unanswered_after_minutes', $1::jsonb)"
        " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        json.dumps(2),
    )


def _lead_plan() -> list[tuple[str, str]]:
    """(stage_key, status) for 30 leads, per STAGE_PLAN."""
    plan: list[tuple[str, str]] = []
    for stage_key, status, count in STAGE_PLAN:
        plan.extend((stage_key, status) for _ in range(count))
    assert len(plan) == TOTAL_LEADS, f"stage plan has {len(plan)} leads"
    return plan


def _in_business_hours(dt: datetime) -> bool:
    local = dt.astimezone(ET)
    return local.weekday() < 5 and 9 <= local.hour < 17


def _force_after_hours(dt: datetime) -> datetime:
    """Move dt outside Mon-Fri 09:00-17:00 ET, keeping the local day if possible."""
    local = dt.astimezone(ET)
    if local.weekday() >= 5:
        return dt  # weekend: already after hours
    if local.hour < 9:
        return dt  # early morning: already after hours
    return local.replace(hour=20, minute=0, second=0, microsecond=0).astimezone(UTC)


def _force_business_hours(dt: datetime) -> datetime:
    """Move dt inside Mon-Fri 09:00-17:00 ET."""
    local = dt.astimezone(ET)
    if local.weekday() >= 5:
        local -= timedelta(days=local.weekday() - 4)  # back to Friday
    if not 9 <= local.hour < 17:
        local = local.replace(hour=12, minute=0, second=0, microsecond=0)
    return local.astimezone(UTC)


async def _clear_demo_rows(conn: asyncpg.Connection) -> None:
    """Delete messages/events of demo leads and the demo leads themselves."""
    wa_ids: list[str] = [
        row[0]
        for row in await conn.fetch(
            "SELECT whatsapp_id FROM tcs_leads WHERE source = $1", DEMO_SOURCE
        )
    ]
    if not wa_ids:
        return
    for table in ("tcs_messages", "tcs_events", "tcs_followups", "tcs_ai_metrics"):
        await conn.execute(f"DELETE FROM {table} WHERE whatsapp_id = ANY($1)", wa_ids)
    await conn.execute("DELETE FROM tcs_leads WHERE source = $1", DEMO_SOURCE)


async def seed_reset(conn: asyncpg.Connection) -> int:
    """--reset: delete only source='demo' rows (leads, messages, events)."""
    count = await conn.fetchval("SELECT COUNT(*) FROM tcs_leads WHERE source = $1", DEMO_SOURCE)
    await _clear_demo_rows(conn)
    return int(count or 0)


async def seed_demo_leads(conn: asyncpg.Connection) -> None:
    """Insert 30 fictional demo leads with messages and events (idempotent).

    Re-running rewrites the demo slice only: demo messages/events are removed
    and re-inserted, so counts stay stable.
    """
    await _clear_demo_rows(conn)

    rng = random.Random(7)
    now = datetime.now(UTC)
    move_in_day = (now + timedelta(days=25)).date()
    move_in = f"{move_in_day:%b} {move_in_day.day}"  # e.g. "Jan 1"
    plan = _lead_plan()
    after_hours_flags = [i < AFTER_HOURS_TARGET for i in range(TOTAL_LEADS)]
    rng.shuffle(after_hours_flags)

    unit_rows = await conn.fetch(
        "SELECT building, unit_number, beds, rent_usd FROM tcs_units ORDER BY id"
    )
    if not unit_rows:
        raise RuntimeError("tcs_units is empty; run the units step first")

    # The single unanswered dialog: NEW_INQUIRY, last message 'in' 30 min ago.
    unanswered_index = 0
    qualified_seen = 0  # three QUALIFIED thinking leads had a past viewing

    lead_rows: list[tuple] = []
    msg_rows: list[tuple] = []
    event_rows: list[tuple] = []
    past_viewings = 0

    for i, ((stage_key, status), after_hours) in enumerate(
        zip(plan, after_hours_flags, strict=True)
    ):
        wa = f"tg:{900_000_000 + i}"
        name = f"{FIRST_NAMES[i]} Demo"
        phone = f"+1 215 555 {100 + i:04d}"
        unit = unit_rows[i % len(unit_rows)]
        building = unit["building"]
        budget = int(unit["rent_usd"] or 2000)
        beds = 1 + i % 3
        pets = "cat" if i % 2 == 0 else "dog" if i % 5 == 0 else "none"

        created_at = now - timedelta(days=1 + (i * 29) // TOTAL_LEADS, hours=3 + i % 5)
        first_msg = (
            _force_after_hours(created_at) if after_hours else _force_business_hours(created_at)
        )
        last_interaction = now - timedelta(
            minutes=30 if i == unanswered_index else 60 * (i % 20 + 2)
        )

        trial: datetime | None = None
        previous_stage: str | None = None
        last_objection: str | None = None

        if stage_key == "NEW_INQUIRY":
            previous_stage = None
        elif stage_key == "QUALIFIED":
            previous_stage = "NEW_INQUIRY"
            if status == "THINKING":
                # Two no-shows and one cancellation come back to Qualified.
                qualified_seen += 1
                past_viewings += 1
                trial = now - timedelta(days=past_viewings + 2)
                last_objection = (
                    "Missed the viewing" if qualified_seen % 2 == 0 else "Plans changed"
                )
            elif status == "ACTIVE":
                last_objection = THINKING_OBJECTIONS[i % len(THINKING_OBJECTIONS)]
        elif stage_key == "VIEWING_SCHEDULED":
            trial = now + timedelta(days=2 + (i % 4))  # 2-5 days out
            previous_stage = "QUALIFIED"
        elif stage_key == "VIEWING_DONE":
            past_viewings += 1
            trial = now - timedelta(days=past_viewings + 2)
            previous_stage = "VIEWING_SCHEDULED"
        elif stage_key == "LEASED":
            past_viewings += 1
            trial = now - timedelta(days=past_viewings + 2)
            previous_stage = "VIEWING_DONE"
        elif stage_key == "LOST":
            previous_stage = "VIEWING_DONE"
            last_objection = (
                "Price too high",
                "Found another place",
                "Not responding",
                "Bad timing",
                "Other",
            )[i % 5]

        if status == "HANDOFF":
            last_objection = "Requested a human"

        lead_rows.append(
            (
                wa,
                name,
                phone,
                status,
                stage_key,
                previous_stage,
                f"{beds}BR · {building} · ${budget:,}",
                f"Move in by {move_in} · budget ${budget:,}",
                f"{beds}BR",
                rng.choice(PREFERRED_TIMES),
                trial,
                last_objection,
                first_msg,
                last_interaction,
                DEMO_SOURCE,
                json.dumps(
                    {
                        "budget_usd": budget,
                        "unit": f"{building} {unit['unit_number']}",
                        "pets": pets,
                    }
                ),
            )
        )

        # --- messages: 2-6 per lead; the last one is outgoing except for the
        # unanswered dialog, whose last message is incoming 30 minutes ago.
        n_messages = rng.randint(2, 6)
        for m in range(n_messages):
            at = first_msg + timedelta(minutes=17 * m + 5)
            if at > now - timedelta(minutes=1):
                at = now - timedelta(minutes=30 if i == unanswered_index else 120)
            direction = "in" if m % 2 == 0 else "out"
            if m == n_messages - 1:
                direction = "in" if i == unanswered_index else "out"
                if i == unanswered_index:
                    at = now - timedelta(minutes=30)  # spec: unanswered ~30 min
            content = rng.choice(IN_CONTENT if direction == "in" else OUT_CONTENT)
            tokens = rng.randint(40, 400) if direction == "out" else None
            response_ms = rng.randint(3000, 12000) if direction == "out" else None
            msg_rows.append((wa, direction, "chat", content, stage_key, tokens, response_ms, at))

        # --- events.
        event_rows.append((wa, "stage_entered", None, "NEW_INQUIRY", "{}", first_msg))
        if previous_stage is not None:
            event_rows.append(
                (wa, "stage_entered", previous_stage, stage_key, "{}", last_interaction)
            )
        if trial is not None:
            booked_at = min(trial, now) - timedelta(hours=1)
            event_rows.append(
                (
                    wa,
                    "trial_booked",
                    None,
                    None,
                    json.dumps({"trial_datetime": trial.isoformat()}),
                    booked_at,
                ),
            )
        if status == "HANDOFF":
            event_rows.append(
                (
                    wa,
                    "transferred_to_manager",
                    None,
                    None,
                    json.dumps({"reason": "Requested a human"}),
                    last_interaction,
                )
            )
        if status == "LOST":
            event_rows.append(
                (
                    wa,
                    "lead_lost",
                    None,
                    None,
                    json.dumps({"reason": last_objection}),
                    last_interaction,
                )
            )
        if status == "LEASED":
            event_rows.append((wa, "sale_won", None, stage_key, "{}", last_interaction))

    await conn.executemany(
        """
        INSERT INTO tcs_leads (
            whatsapp_id, client_name, phone, status, current_stage, previous_stage,
            direction, goal, preferred_format, preferred_time, trial_datetime,
            last_objection, created_at, last_interaction_at, source, lead_data
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                  $16::jsonb)
        ON CONFLICT (whatsapp_id) DO UPDATE SET
            client_name = EXCLUDED.client_name, phone = EXCLUDED.phone,
            status = EXCLUDED.status, current_stage = EXCLUDED.current_stage,
            previous_stage = EXCLUDED.previous_stage, direction = EXCLUDED.direction,
            goal = EXCLUDED.goal, preferred_format = EXCLUDED.preferred_format,
            preferred_time = EXCLUDED.preferred_time,
            trial_datetime = EXCLUDED.trial_datetime,
            last_objection = EXCLUDED.last_objection,
            last_interaction_at = EXCLUDED.last_interaction_at,
            source = EXCLUDED.source, lead_data = EXCLUDED.lead_data
        """,
        lead_rows,
    )
    await conn.executemany(
        """
        INSERT INTO tcs_messages (
            whatsapp_id, direction, message_type, content, stage_at_moment,
            tokens_used, response_time_ms, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        msg_rows,
    )
    await conn.executemany(
        """
        INSERT INTO tcs_events (
            whatsapp_id, event_type, from_stage, to_stage, payload, created_at
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
        """,
        event_rows,
    )


async def ensure_bot_tool_tables(conn: asyncpg.Connection) -> None:
    """Tables used by the bot's book_viewing / handoff_to_human tools."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS viewing_bookings (
            id BIGSERIAL PRIMARY KEY,
            client_name TEXT,
            client_phone TEXT,
            unit_id TEXT,
            viewing_date DATE,
            viewing_time TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS manager_handoffs (
            id BIGSERIAL PRIMARY KEY,
            client_phone TEXT,
            reason TEXT,
            conversation_summary TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


async def run_seed(conn: asyncpg.Connection) -> dict[str, int]:
    """Seed everything; every step is idempotent. Returns counters."""
    await ensure_bot_tool_tables(conn)
    await seed_settings(conn)
    units = await seed_units(conn)
    await seed_demo_leads(conn)
    leads = await conn.fetchval("SELECT COUNT(*) FROM tcs_leads WHERE source = $1", DEMO_SOURCE)
    messages = await conn.fetchval(
        "SELECT COUNT(*) FROM tcs_messages"
        " WHERE whatsapp_id IN (SELECT whatsapp_id FROM tcs_leads WHERE source = $1)",
        DEMO_SOURCE,
    )
    return {"units": units, "leads": int(leads), "messages": int(messages)}


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete only demo rows")
    args = parser.parse_args(argv)

    error = confirm_error()
    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(dsn=_dsn())
        if error is None and not args.reset:
            error = await schema_error(conn)
        if error is None and not args.reset:
            error = await pipeline_error(conn)
        if error is not None:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        if args.reset:
            removed = await seed_reset(conn)
            print(f"Reset OK: removed {removed} demo lead(s)")
        else:
            stats = await run_seed(conn)
            print(f"Seed OK: {stats}")
        return 0
    finally:
        if conn is not None:
            await conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:  # pragma: no cover - CLI wrapper
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
