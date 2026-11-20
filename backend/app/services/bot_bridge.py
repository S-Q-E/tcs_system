from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MANUAL_STAGE_CHANGE_EVENT = "manual_stage_change"


class BotLeadNotFoundError(LookupError):
    """Raised when the target lead does not exist in tcs_leads."""


async def update_bot_stage(
    session: AsyncSession,
    whatsapp_id: str,
    stage_key: str,
    changed_by: uuid.UUID | None,
) -> bool:
    """Push a manager-driven stage change into the bot tables (D3).

    Updates ``tcs_leads.current_stage``/``previous_stage`` and appends a
    ``manual_stage_change`` row to ``tcs_events`` in the caller's
    transaction (no commit here). Returns True when something changed,
    False when the lead already sits on ``stage_key``.

    This module is the ONLY place allowed to write to ``tcs_*`` tables.
    """
    row = (
        await session.execute(
            text(
                "SELECT current_stage FROM tcs_leads" " WHERE whatsapp_id = :whatsapp_id FOR UPDATE"
            ),
            {"whatsapp_id": whatsapp_id},
        )
    ).one_or_none()
    if row is None:
        raise BotLeadNotFoundError(f"Bot lead not found: {whatsapp_id}")
    from_stage: str | None = row[0]
    if from_stage == stage_key:
        return False

    now = datetime.now(UTC)
    await session.execute(
        text(
            "UPDATE tcs_leads SET previous_stage = current_stage,"
            " current_stage = :stage_key, updated_at = :now"
            " WHERE whatsapp_id = :whatsapp_id"
        ),
        {"stage_key": stage_key, "now": now, "whatsapp_id": whatsapp_id},
    )
    payload = {"user_id": str(changed_by) if changed_by is not None else None}
    await session.execute(
        text(
            "INSERT INTO tcs_events"
            " (whatsapp_id, event_type, from_stage, to_stage, payload, created_at)"
            " VALUES (:whatsapp_id, :event_type, :from_stage, :to_stage,"
            " CAST(:payload AS jsonb), :now)"
        ),
        {
            "whatsapp_id": whatsapp_id,
            "event_type": MANUAL_STAGE_CHANGE_EVENT,
            "from_stage": from_stage,
            "to_stage": stage_key,
            "payload": _json(payload),
            "now": now,
        },
    )
    logger.info("bot stage updated from=%s to=%s", from_stage, stage_key)
    return True


async def insert_outgoing_message(session: AsyncSession, whatsapp_id: str, body: str) -> int:
    """Mirror a manager-sent outbox message into the bot tables (D6).

    Appends a ``direction='out', message_type='manager'`` row to
    ``tcs_messages`` stamped with the lead's current stage, in the
    caller's transaction (no commit here). Returns the new message id.
    This module is the ONLY place allowed to write to ``tcs_*`` tables.
    """
    row = (
        await session.execute(
            text(
                "SELECT current_stage FROM tcs_leads" " WHERE whatsapp_id = :whatsapp_id FOR UPDATE"
            ),
            {"whatsapp_id": whatsapp_id},
        )
    ).one_or_none()
    if row is None:
        raise BotLeadNotFoundError(f"Bot lead not found: {whatsapp_id}")
    message_id = (
        await session.execute(
            text(
                "INSERT INTO tcs_messages"
                " (whatsapp_id, direction, message_type, content,"
                " stage_at_moment, tokens_used, created_at)"
                " VALUES (:whatsapp_id, 'out', 'manager', :content,"
                " :stage, 0, :now) RETURNING id"
            ),
            {
                "whatsapp_id": whatsapp_id,
                "content": body,
                "stage": row[0],
                "now": datetime.now(UTC),
            },
        )
    ).scalar_one()
    # Never log message bodies or phone numbers (whatsapp_id).
    logger.info("manager message mirrored message_id=%s", message_id)
    return int(message_id)


async def book_viewing(
    session: AsyncSession,
    *,
    whatsapp_id: str | None,
    slot_id: uuid.UUID,
    unit_id: uuid.UUID | None = None,
    client_name: str | None = None,
    client_phone: str | None = None,
    deal_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    notes: str | None = None,
    created_by: uuid.UUID | None = None,
) -> tuple[str, uuid.UUID | None]:
    """Atomically book a viewing slot via Postgres function tcs_crm_book_viewing."""
    row = (
        await session.execute(
            text(
                "SELECT result, booking_id FROM tcs_crm_book_viewing("
                " :whatsapp_id, :slot_id, :unit_id, :client_name, :client_phone,"
                " :deal_id, :contact_id, :notes, :created_by)"
            ),
            {
                "whatsapp_id": whatsapp_id,
                "slot_id": slot_id,
                "unit_id": unit_id,
                "client_name": client_name,
                "client_phone": client_phone,
                "deal_id": deal_id,
                "contact_id": contact_id,
                "notes": notes,
                "created_by": created_by,
            },
        )
    ).one()
    return str(row[0]), row[1]


async def cancel_viewing(
    session: AsyncSession,
    *,
    booking_id: uuid.UUID,
    reason: str | None = None,
) -> tuple[str, uuid.UUID | None]:
    """Atomically cancel a viewing booking via Postgres function tcs_crm_cancel_viewing."""
    row = (
        await session.execute(
            text("SELECT result, booking_id FROM tcs_crm_cancel_viewing(:booking_id, :reason)"),
            {"booking_id": booking_id, "reason": reason},
        )
    ).one()
    return str(row[0]), row[1]


async def reschedule_viewing(
    session: AsyncSession,
    *,
    booking_id: uuid.UUID,
    new_slot_id: uuid.UUID,
) -> tuple[str, uuid.UUID | None]:
    """Atomically reschedule a viewing via Postgres function tcs_crm_reschedule_viewing."""
    row = (
        await session.execute(
            text(
                "SELECT result, booking_id FROM tcs_crm_reschedule_viewing("
                " :booking_id, :new_slot_id)"
            ),
            {"booking_id": booking_id, "new_slot_id": new_slot_id},
        )
    ).one()
    return str(row[0]), row[1]


def _json(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
