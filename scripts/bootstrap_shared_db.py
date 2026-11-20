"""Bootstrap a shared CRM + bot database after the tcs_ table-prefix rename.

The demo CRM expects ``tcs_crm_*`` tables (Alembic) and the bot owns
``tcs_leads`` / ``tcs_messages`` / ``tcs_events`` / ``tcs_units``. This script
is for a database that already exists:

* renames the legacy ``crm_*`` tables (and the version table) to ``tcs_crm_*``
  instead of recreating them, so CRM data survives the prefix change;
* drops the empty ``tcs_crm_*`` tables Alembic created before the rename;
* renames ``n8n_processed_outbox`` to ``tcs_n8n_processed_outbox``;
* creates the bot tables when they are missing (schema only, never demo rows);
* creates the tables used by the bot's booking and handoff tools.

It is idempotent: once the tables carry the new prefix, a re-run is a no-op.
The bot workflow must use the same names (see the updated workflow JSON):
``tcs_crm_conversation_state`` and ``tcs_n8n_processed_outbox``.

Usage:
    SHARED_DB_CONFIRM=I_UNDERSTAND_THIS_IS_THE_SHARED_BOT_DB \
        python scripts/bootstrap_shared_db.py --apply

Without ``--apply`` the script only prints the detected state.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

CONFIRM_ENV = "SHARED_DB_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_IS_THE_SHARED_BOT_DB"

ROOT = Path(__file__).resolve().parents[1]
BOT_SCHEMA_SQL = ROOT / "tests" / "fixtures" / "tcs_schema.sql"

UNITS_SQL = """
CREATE TABLE IF NOT EXISTS tcs_units (
    id SERIAL PRIMARY KEY,
    building TEXT NOT NULL,
    unit_number TEXT NOT NULL,
    beds INT NOT NULL,
    baths NUMERIC NOT NULL DEFAULT 1,
    rent_usd INT NOT NULL,
    deposit_usd INT NOT NULL,
    available_from DATE DEFAULT CURRENT_DATE,
    pets_policy TEXT DEFAULT 'Pets allowed with deposit',
    description TEXT,
    status TEXT NOT NULL DEFAULT 'available',
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (building, unit_number)
)
"""

BOOKING_SQL = """
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

HANDOFF_SQL = """
CREATE TABLE IF NOT EXISTS manager_handoffs (
    id BIGSERIAL PRIMARY KEY,
    client_phone TEXT,
    reason TEXT,
    conversation_summary TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


async def _tables(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {row["tablename"] for row in rows}


async def _rename_tables(
    conn: asyncpg.Connection, old_prefix: str, new_prefix: str, skip: set[str] = frozenset()
) -> list[tuple[str, str]]:
    renamed: list[tuple[str, str]] = []
    for name in sorted(await _tables(conn)):
        if not name.startswith(old_prefix) or name in skip:
            continue
        target = new_prefix + name[len(old_prefix) :]
        await conn.execute(f'ALTER TABLE "{name}" RENAME TO "{target}"')
        renamed.append((name, target))
    return renamed


async def bootstrap(conn: asyncpg.Connection) -> None:
    tables = await _tables(conn)

    legacy_crm = any(name.startswith("crm_") for name in tables)
    new_crm = sorted(name for name in tables if name.startswith("tcs_crm_"))
    if not legacy_crm and not new_crm:
        print("No CRM tables found: run `alembic upgrade head` first.")
        return

    if legacy_crm and new_crm:
        # New tables were created by Alembic before the rename. They are
        # expected to be empty; refuse to drop anything that carries data.
        for name in new_crm:
            count = await conn.fetchval(f'SELECT COUNT(*) FROM "{name}"')
            if count:
                raise SystemExit(
                    f'Refusing to drop "{name}": it has {count} row(s). '
                    "Resolve the two CRM schemas by hand first."
                )
        for name in new_crm:
            await conn.execute(f'DROP TABLE "{name}" CASCADE')
        print(f"Dropped {len(new_crm)} empty tcs_crm_* table(s).")

    if legacy_crm:
        renamed = await _rename_tables(conn, "crm_", "tcs_crm_", skip={"crm_alembic_version"})
        await conn.execute('ALTER TABLE "crm_alembic_version" RENAME TO "tcs_crm_alembic_version"')
        print(f"Renamed {len(renamed)} crm_* table(s) to tcs_crm_*.")

    tables = await _tables(conn)

    if "n8n_processed_outbox" in tables and "tcs_n8n_processed_outbox" not in tables:
        await conn.execute(
            'ALTER TABLE "n8n_processed_outbox" RENAME TO "tcs_n8n_processed_outbox"'
        )
        print("Renamed n8n_processed_outbox to tcs_n8n_processed_outbox.")

    if "tcs_leads" not in tables:
        await conn.execute(BOT_SCHEMA_SQL.read_text(encoding="utf-8"))
        print("Created the bot schema (tcs_leads, tcs_messages, tcs_events, ...).")

    await conn.execute(UNITS_SQL)
    await conn.execute(BOOKING_SQL)
    await conn.execute(HANDOFF_SQL)
    print("Ensured tcs_units, viewing_bookings and manager_handoffs exist.")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="perform the changes (default: dry run)"
    )
    args = parser.parse_args(argv)

    if os.environ.get(CONFIRM_ENV) != CONFIRM_VALUE:
        print(
            f"Refusing to run: set {CONFIRM_ENV}={CONFIRM_VALUE} to confirm this "
            "is the shared bot database."
        )
        return 2

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set")
        return 2

    conn = await asyncpg.connect(dsn)
    try:
        if not args.apply:
            tables = sorted(await _tables(conn))
            crm = [t for t in tables if t.startswith(("crm_", "tcs_crm_"))]
            bot = [t for t in tables if t.startswith(("tcs_leads", "tcs_messages"))]
            print("Dry run; pass --apply to change the database.")
            print(f"CRM tables: {crm or 'none'}")
            print(f"Bot tables: {bot or 'none'}")
            return 0
        async with conn.transaction():
            await bootstrap(conn)
        counts = {}
        for table in ("tcs_crm_users", "tcs_crm_deals", "tcs_crm_contacts"):
            try:
                counts[table] = await conn.fetchval(f'SELECT COUNT(*) FROM "{table}"')
            except asyncpg.UndefinedTableError:
                counts[table] = None
        print(f"Done: {counts}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
