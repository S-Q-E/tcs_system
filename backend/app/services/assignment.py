from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CrmContact, CrmDeal
from .notifications import active_managers

logger = logging.getLogger(__name__)

SETTING_ASSIGNMENT = "deal_assignment"

MODE_UNASSIGNED = "unassigned"
MODE_ROUND_ROBIN = "round_robin"


async def get_assignment_mode(session: AsyncSession) -> str:
    row = (
        await session.execute(
            text("SELECT value FROM tcs_crm_settings WHERE key = :key"), {"key": SETTING_ASSIGNMENT}
        )
    ).scalar_one_or_none()
    if isinstance(row, dict) and row.get("mode") == MODE_ROUND_ROBIN:
        return MODE_ROUND_ROBIN
    return MODE_UNASSIGNED


async def pick_assignee(session: AsyncSession) -> uuid.UUID | None:
    """Round-robin pick among active managers; None when disabled or empty.

    The settings row is locked (SELECT ... FOR UPDATE, seeded by migration
    ``0013_round_robin``) so concurrent picks serialize: read, rotate and
    store happen atomically within the caller's transaction. No commit here.
    """
    row = (
        await session.execute(
            text("SELECT value FROM tcs_crm_settings WHERE key = :key FOR UPDATE"),
            {"key": SETTING_ASSIGNMENT},
        )
    ).scalar_one_or_none()
    if not (isinstance(row, dict) and row.get("mode") == MODE_ROUND_ROBIN):
        return None
    managers = await active_managers(session)
    if not managers:
        return None
    last_index = row.get("last_index")
    if not isinstance(last_index, int):
        last_index = -1
    # The roster may change; rotate by position, not by stored user.
    next_index = (last_index + 1) % len(managers)
    picked = managers[next_index][0]
    await session.execute(
        text(
            "INSERT INTO tcs_crm_settings (key, value) VALUES (:key, CAST(:value AS jsonb))"
            " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
        ),
        {
            "key": SETTING_ASSIGNMENT,
            "value": json.dumps({"mode": MODE_ROUND_ROBIN, "last_index": next_index}),
        },
    )
    logger.info("round-robin assigned user=%s", picked)
    return picked


async def _sync_state(
    session: AsyncSession, whatsapp_id: str | None, owner_id: uuid.UUID | None
) -> None:
    """Write the owner into tcs_crm_conversation_state (bot leads only)."""
    if not whatsapp_id:
        return
    await session.execute(
        text(
            "INSERT INTO tcs_crm_conversation_state (whatsapp_id, assigned_to)"
            " SELECT :wa, CAST(:owner AS uuid)"
            " WHERE EXISTS (SELECT 1 FROM tcs_leads WHERE whatsapp_id = :wa)"
            " ON CONFLICT (whatsapp_id) DO UPDATE SET assigned_to = EXCLUDED.assigned_to"
        ),
        {"wa": whatsapp_id, "owner": str(owner_id) if owner_id else None},
    )


async def set_deal_owner(session: AsyncSession, deal: CrmDeal, owner_id: uuid.UUID | None) -> None:
    """The deal is the source of truth. Writes the owner to deal, contact and dialog. No commit."""
    deal.owner_id = owner_id
    contact = await session.get(CrmContact, deal.contact_id)
    if contact is None:
        return
    contact.owner_id = owner_id
    await _sync_state(session, contact.whatsapp_id, owner_id)


async def set_contact_owner(
    session: AsyncSession, contact: CrmContact, owner_id: uuid.UUID | None
) -> None:
    """Assignment from a contact/dialog goes to the newest live deal of the contact.

    If the contact has no live deals, write only to the contact and the dialog.
    """
    deal = (
        await session.execute(
            select(CrmDeal)
            .where(CrmDeal.contact_id == contact.id, CrmDeal.deleted_at.is_(None))
            .order_by(CrmDeal.updated_at.desc(), CrmDeal.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if deal is not None:
        await set_deal_owner(session, deal, owner_id)
    else:
        contact.owner_id = owner_id
        await _sync_state(session, contact.whatsapp_id, owner_id)
