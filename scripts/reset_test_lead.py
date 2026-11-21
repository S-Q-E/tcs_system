"""Reset one demo/test lead to a clean starting state.

Cancels active viewings through `tcs_crm_cancel_viewing`, resets the lead row,
unpauses the bot and clears the n8n chat memory for that session.

Safety:
- refuses to run unless DEMO_DB_CONFIRM=I_UNDERSTAND_THIS_IS_A_DEMO_DB;
- touches only the single whatsapp_id passed on the command line.

Run: DEMO_DB_CONFIRM=I_UNDERSTAND_THIS_IS_A_DEMO_DB \
     python scripts/reset_test_lead.py --whatsapp-id tg:563779188
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import asyncpg

CONFIRM_ENV = "DEMO_DB_CONFIRM"
CONFIRM_VALUE = "I_UNDERSTAND_THIS_IS_A_DEMO_DB"


def _dsn() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://tcs:tcs@localhost:5432/tcs")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def confirm_error(env: dict[str, str] | None = None) -> str | None:
    env = os.environ if env is None else env
    if env.get(CONFIRM_ENV) != CONFIRM_VALUE:
        return (
            f"Refusing to run: set {CONFIRM_ENV}={CONFIRM_VALUE}"
            " to confirm this is a demo database."
        )
    return None


async def reset_lead(conn: asyncpg.Connection, whatsapp_id: str) -> dict[str, Any]:
    """Reset one lead, its active bookings, bot pause flag and chat memory."""
    bookings = await conn.fetch(
        "SELECT id FROM tcs_crm_viewing_bookings"
        " WHERE whatsapp_id = $1 AND status IN ('pending', 'confirmed')"
        " ORDER BY created_at",
        whatsapp_id,
    )
    cancelled: list[str] = []
    for row in bookings:
        result = await conn.fetchval(
            "SELECT result FROM tcs_crm_cancel_viewing($1, 'test reset')", row["id"]
        )
        cancelled.append(str(result))

    lead = await conn.fetchrow(
        """
        UPDATE tcs_leads
           SET status = 'ACTIVE',
               current_stage = 'NEW_INQUIRY',
               previous_stage = NULL,
               trial_datetime = NULL,
               reminder_sent = false,
               last_objection = NULL,
               lead_data = '{}'::jsonb,
               updated_at = now()
         WHERE whatsapp_id = $1
         RETURNING whatsapp_id, status, current_stage, previous_stage,
                   trial_datetime, lead_data
        """,
        whatsapp_id,
    )

    state = await conn.fetchrow(
        """
        INSERT INTO tcs_crm_conversation_state (whatsapp_id, bot_paused, paused_by, paused_at)
        VALUES ($1, false, NULL, NULL)
        ON CONFLICT (whatsapp_id) DO UPDATE
          SET bot_paused = false, paused_by = NULL, paused_at = NULL
        RETURNING whatsapp_id, bot_paused
        """,
        whatsapp_id,
    )

    chat_rows = 0
    if await conn.fetchval("SELECT to_regclass('public.n8n_chat_histories')") is not None:
        deleted = await conn.fetch(
            "DELETE FROM n8n_chat_histories WHERE session_id = $1 RETURNING id",
            whatsapp_id,
        )
        chat_rows = len(deleted)

    return {
        "whatsapp_id": whatsapp_id,
        "cancelled_bookings": cancelled,
        "lead": dict(lead) if lead else None,
        "state": dict(state) if state else None,
        "chat_rows_deleted": chat_rows,
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--whatsapp-id", required=True, help="e.g. tg:563779188")
    args = parser.parse_args(argv)

    error = confirm_error()
    if error is not None:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn=_dsn())
    try:
        summary = await reset_lead(conn, args.whatsapp_id)
    finally:
        await conn.close()
    print("Reset OK:", json.dumps(summary, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:  # pragma: no cover - CLI wrapper
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
