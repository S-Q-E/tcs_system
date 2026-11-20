from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_deps import CurrentUser, require_role, require_user
from ..deps import get_session
from ..errors import ApiError
from ..models import (
    ACTIVE_BOOKING_STATUSES,
    SLOT_STATUS_BOOKED,
    CrmUnit,
    CrmViewingBooking,
    CrmViewingSlot,
)
from ..schemas.viewings import (
    SlotBookingBriefOut,
    ViewingBookingCancelIn,
    ViewingBookingCreate,
    ViewingBookingListOut,
    ViewingBookingOut,
    ViewingBookingRescheduleIn,
    ViewingBookingUpdate,
    ViewingSlotCreate,
    ViewingSlotGenerateIn,
    ViewingSlotGenerateOut,
    ViewingSlotListOut,
    ViewingSlotOut,
    ViewingSlotUpdate,
)
from ..services import bot_bridge
from ..services.activity import diff_payload, log_activity, slim
from ..services.slots import generate_slots

slots_router = APIRouter(prefix="/api/viewing-slots", tags=["viewing-slots"])
bookings_router = APIRouter(prefix="/api/viewing-bookings", tags=["viewing-bookings"])

require_admin = require_role("admin")


def _unit_label(unit: CrmUnit | None) -> str | None:
    if unit is None:
        return None
    return f"{unit.building} {unit.unit_number}"


def _slot_snapshot(slot: CrmViewingSlot) -> dict:
    return slim(
        {
            "starts_at": slot.starts_at,
            "duration_min": slot.duration_min,
            "unit_id": slot.unit_id,
            "status": slot.status,
        }
    )


def _booking_snapshot(booking: CrmViewingBooking) -> dict:
    return slim(
        {
            "slot_id": booking.slot_id,
            "unit_id": booking.unit_id,
            "deal_id": booking.deal_id,
            "contact_id": booking.contact_id,
            "whatsapp_id": booking.whatsapp_id,
            "client_name": booking.client_name,
            "client_phone": booking.client_phone,
            "status": booking.status,
            "notes": booking.notes,
            "cancelled_at": booking.cancelled_at,
        }
    )


def _ensure_future(dt: datetime) -> datetime:
    normalized = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    if normalized <= datetime.now(UTC):
        raise ApiError("SLOT_IN_PAST", "Viewing slot must be in the future", 400)
    return normalized


async def _load_units_map(
    session: AsyncSession, unit_ids: set[uuid.UUID]
) -> dict[uuid.UUID, CrmUnit]:
    if not unit_ids:
        return {}
    rows = (await session.execute(select(CrmUnit).where(CrmUnit.id.in_(unit_ids)))).scalars().all()
    return {u.id: u for u in rows}


async def _booking_out(
    session: AsyncSession, booking: CrmViewingBooking
) -> ViewingBookingOut:
    slot = await session.get(CrmViewingSlot, booking.slot_id)
    unit = await session.get(CrmUnit, booking.unit_id) if booking.unit_id else None
    out = ViewingBookingOut.model_validate(booking)
    if slot is not None:
        out.slot_starts_at = slot.starts_at
        out.slot_duration_min = slot.duration_min
    out.unit_label = _unit_label(unit)
    return out


def _raise_for_fn_result(result: str) -> None:
    if result == "slot_not_found":
        raise ApiError("NOT_FOUND", "Viewing slot not found", 404)
    if result == "booking_not_found":
        raise ApiError("NOT_FOUND", "Viewing booking not found", 404)
    if result == "lead_not_found":
        raise ApiError("LEAD_NOT_FOUND", "Bot lead not found for whatsapp_id", 404)
    if result == "slot_in_past":
        raise ApiError("SLOT_IN_PAST", "Viewing slot is in the past", 400)
    if result == "slot_taken":
        raise ApiError("SLOT_TAKEN", "Viewing slot is no longer available", 409)
    if result == "unit_mismatch":
        raise ApiError("UNIT_MISMATCH", "Slot is reserved for a different unit", 409)
    if result in ("already_cancelled", "not_active"):
        raise ApiError("BOOKING_NOT_ACTIVE", f"Booking cannot be modified ({result})", 409)


# --------------------------------------------------------------- viewing slots


@slots_router.get("", response_model=ViewingSlotListOut)
async def list_viewing_slots(
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    status: str | None = Query(default=None, pattern="^(open|booked|blocked)$"),
    unit_id: uuid.UUID | None = None,
    only_future: bool = False,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    del user
    stmt = select(CrmViewingSlot)
    if from_at is not None:
        stmt = stmt.where(CrmViewingSlot.starts_at >= from_at)
    if to_at is not None:
        stmt = stmt.where(CrmViewingSlot.starts_at <= to_at)
    if only_future:
        stmt = stmt.where(CrmViewingSlot.starts_at > datetime.now(UTC))
    if status is not None:
        stmt = stmt.where(CrmViewingSlot.status == status)
    if unit_id is not None:
        stmt = stmt.where(CrmViewingSlot.unit_id == unit_id)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    slots = (
        (
            await session.execute(
                stmt.order_by(CrmViewingSlot.starts_at.asc(), CrmViewingSlot.id.asc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    slot_ids = [s.id for s in slots]
    active_by_slot: dict[uuid.UUID, CrmViewingBooking] = {}
    if slot_ids:
        bookings = (
            (
                await session.execute(
                    select(CrmViewingBooking).where(
                        CrmViewingBooking.slot_id.in_(slot_ids),
                        CrmViewingBooking.status.in_(ACTIVE_BOOKING_STATUSES),
                    )
                )
            )
            .scalars()
            .all()
        )
        active_by_slot = {b.slot_id: b for b in bookings}

    unit_ids = {s.unit_id for s in slots if s.unit_id is not None} | {
        b.unit_id for b in active_by_slot.values() if b.unit_id is not None
    }
    units_map = await _load_units_map(session, unit_ids)

    items: list[ViewingSlotOut] = []
    for slot in slots:
        out = ViewingSlotOut.model_validate(slot)
        out.unit_label = _unit_label(units_map.get(slot.unit_id)) if slot.unit_id else None
        booking = active_by_slot.get(slot.id)
        if booking is not None:
            out.booking = SlotBookingBriefOut(
                id=booking.id,
                status=booking.status,
                unit_id=booking.unit_id,
                unit_label=_unit_label(units_map.get(booking.unit_id)) if booking.unit_id else None,
                deal_id=booking.deal_id,
                contact_id=booking.contact_id,
                whatsapp_id=booking.whatsapp_id,
                client_name=booking.client_name,
                client_phone=booking.client_phone,
                notes=booking.notes,
            )
        items.append(out)
    return ViewingSlotListOut(items=items, total=int(total))


@slots_router.post("", response_model=ViewingSlotOut, status_code=201)
async def create_viewing_slot(
    payload: ViewingSlotCreate,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    starts_at = _ensure_future(payload.starts_at)
    unit: CrmUnit | None = None
    if payload.unit_id is not None:
        unit = await session.get(CrmUnit, payload.unit_id)
        if unit is None or unit.deleted_at is not None:
            raise ApiError("NOT_FOUND", "Unit not found", 404)

    slot = CrmViewingSlot(
        starts_at=starts_at,
        duration_min=payload.duration_min,
        unit_id=payload.unit_id,
        status=payload.status,
        created_by=admin.id,
    )
    session.add(slot)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError("SLOT_TAKEN", "A slot at this time already exists", 409) from exc

    await log_activity(
        session,
        admin.id,
        "viewing_slot",
        slot.id,
        "slot_created",
        diff_payload(None, _slot_snapshot(slot)),
    )
    await session.commit()
    await session.refresh(slot)
    out = ViewingSlotOut.model_validate(slot)
    out.unit_label = _unit_label(unit)
    return out


@slots_router.post("/generate", response_model=ViewingSlotGenerateOut)
async def generate_viewing_slots(
    payload: ViewingSlotGenerateIn | None = None,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    body = payload or ViewingSlotGenerateIn()
    if body.unit_id is not None:
        unit = await session.get(CrmUnit, body.unit_id)
        if unit is None or unit.deleted_at is not None:
            raise ApiError("NOT_FOUND", "Unit not found", 404)

    created, total_candidates = await generate_slots(
        session,
        days=body.days,
        unit_id=body.unit_id,
        created_by=admin.id,
        duration_min=body.duration_min,
    )
    await log_activity(
        session,
        admin.id,
        "viewing_slot",
        None,
        "slots_generated",
        {
            "days": body.days,
            "duration_min": body.duration_min,
            "unit_id": body.unit_id,
            "created": created,
            "total_candidates": total_candidates,
        },
    )
    await session.commit()
    return ViewingSlotGenerateOut(created=created, total_candidates=total_candidates)


@slots_router.patch("/{slot_id}", response_model=ViewingSlotOut)
async def update_viewing_slot(
    slot_id: uuid.UUID,
    payload: ViewingSlotUpdate,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    slot = await session.get(CrmViewingSlot, slot_id)
    if slot is None:
        raise ApiError("NOT_FOUND", "Viewing slot not found", 404)

    has_active = (
        await session.execute(
            select(func.count())
            .select_from(CrmViewingBooking)
            .where(
                CrmViewingBooking.slot_id == slot.id,
                CrmViewingBooking.status.in_(ACTIVE_BOOKING_STATUSES),
            )
        )
    ).scalar() or 0
    if has_active > 0 or slot.status == SLOT_STATUS_BOOKED:
        raise ApiError("SLOT_TAKEN", "Cannot modify a booked viewing slot", 409)

    before = _slot_snapshot(slot)
    fields = payload.model_fields_set
    if "starts_at" in fields and payload.starts_at is not None:
        slot.starts_at = _ensure_future(payload.starts_at)
    if "duration_min" in fields and payload.duration_min is not None:
        slot.duration_min = payload.duration_min
    if "unit_id" in fields:
        if payload.unit_id is not None:
            unit = await session.get(CrmUnit, payload.unit_id)
            if unit is None or unit.deleted_at is not None:
                raise ApiError("NOT_FOUND", "Unit not found", 404)
        slot.unit_id = payload.unit_id
    if "status" in fields and payload.status is not None:
        slot.status = payload.status

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError("SLOT_TAKEN", "A slot at this time already exists", 409) from exc

    await log_activity(
        session,
        admin.id,
        "viewing_slot",
        slot.id,
        "slot_updated",
        diff_payload(before, _slot_snapshot(slot)),
    )
    await session.commit()
    await session.refresh(slot)
    unit = await session.get(CrmUnit, slot.unit_id) if slot.unit_id else None
    out = ViewingSlotOut.model_validate(slot)
    out.unit_label = _unit_label(unit)
    return out


@slots_router.delete("/{slot_id}")
async def delete_viewing_slot(
    slot_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    slot = await session.get(CrmViewingSlot, slot_id)
    if slot is None:
        raise ApiError("NOT_FOUND", "Viewing slot not found", 404)

    bookings_count = (
        await session.execute(
            select(func.count())
            .select_from(CrmViewingBooking)
            .where(CrmViewingBooking.slot_id == slot.id)
        )
    ).scalar() or 0
    if bookings_count > 0 or slot.status == SLOT_STATUS_BOOKED:
        raise ApiError(
            "SLOT_TAKEN",
            "Cannot delete a slot that has viewing bookings",
            409,
            {"bookings": int(bookings_count)},
        )

    before = _slot_snapshot(slot)
    await log_activity(
        session,
        admin.id,
        "viewing_slot",
        slot.id,
        "slot_deleted",
        diff_payload(before, None),
    )
    await session.delete(slot)
    await session.commit()
    return {"ok": True}


# ------------------------------------------------------------ viewing bookings


@bookings_router.get("", response_model=ViewingBookingListOut)
async def list_viewing_bookings(
    deal_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    whatsapp_id: str | None = None,
    unit_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, pattern="^(pending|confirmed|cancelled|no_show)$"),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    del user
    stmt = select(CrmViewingBooking).join(
        CrmViewingSlot, CrmViewingSlot.id == CrmViewingBooking.slot_id
    )
    if deal_id is not None:
        stmt = stmt.where(CrmViewingBooking.deal_id == deal_id)
    if contact_id is not None:
        stmt = stmt.where(CrmViewingBooking.contact_id == contact_id)
    if whatsapp_id is not None:
        stmt = stmt.where(CrmViewingBooking.whatsapp_id == whatsapp_id)
    if unit_id is not None:
        stmt = stmt.where(CrmViewingBooking.unit_id == unit_id)
    if status is not None:
        stmt = stmt.where(CrmViewingBooking.status == status)
    if from_at is not None:
        stmt = stmt.where(CrmViewingSlot.starts_at >= from_at)
    if to_at is not None:
        stmt = stmt.where(CrmViewingSlot.starts_at <= to_at)

    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    bookings = (
        (
            await session.execute(
                stmt.order_by(CrmViewingSlot.starts_at.desc(), CrmViewingBooking.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    slot_ids = {b.slot_id for b in bookings}
    slots_map: dict[uuid.UUID, CrmViewingSlot] = {}
    if slot_ids:
        slot_rows = (
            (await session.execute(select(CrmViewingSlot).where(CrmViewingSlot.id.in_(slot_ids))))
            .scalars()
            .all()
        )
        slots_map = {s.id: s for s in slot_rows}
    units_map = await _load_units_map(
        session, {b.unit_id for b in bookings if b.unit_id is not None}
    )

    items: list[ViewingBookingOut] = []
    for booking in bookings:
        out = ViewingBookingOut.model_validate(booking)
        slot = slots_map.get(booking.slot_id)
        if slot is not None:
            out.slot_starts_at = slot.starts_at
            out.slot_duration_min = slot.duration_min
        out.unit_label = _unit_label(units_map.get(booking.unit_id)) if booking.unit_id else None
        items.append(out)
    return ViewingBookingListOut(items=items, total=int(total))


@bookings_router.post("", response_model=ViewingBookingOut, status_code=201)
async def create_viewing_booking(
    payload: ViewingBookingCreate,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    result, booking_id = await bot_bridge.book_viewing(
        session,
        whatsapp_id=payload.whatsapp_id,
        slot_id=payload.slot_id,
        unit_id=payload.unit_id,
        client_name=payload.client_name,
        client_phone=payload.client_phone,
        deal_id=payload.deal_id,
        contact_id=payload.contact_id,
        notes=payload.notes,
        created_by=user.id,
    )
    if result != "booked" or booking_id is None:
        await session.rollback()
        _raise_for_fn_result(result)

    booking = await session.get(CrmViewingBooking, booking_id)
    assert booking is not None
    await log_activity(
        session,
        user.id,
        "viewing_booking",
        booking.id,
        "booking_created",
        diff_payload(None, _booking_snapshot(booking)),
    )
    await session.commit()
    await session.refresh(booking)
    return await _booking_out(session, booking)


@bookings_router.patch("/{booking_id}", response_model=ViewingBookingOut)
async def update_viewing_booking(
    booking_id: uuid.UUID,
    payload: ViewingBookingUpdate,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    booking = await session.get(CrmViewingBooking, booking_id)
    if booking is None:
        raise ApiError("NOT_FOUND", "Viewing booking not found", 404)
    before = _booking_snapshot(booking)
    fields = payload.model_fields_set
    if "status" in fields and payload.status is not None:
        if booking.status == "cancelled":
            raise ApiError("BOOKING_NOT_ACTIVE", "Cancelled booking cannot be updated", 409)
        booking.status = payload.status
    if "notes" in fields:
        booking.notes = payload.notes
    if "client_name" in fields:
        booking.client_name = payload.client_name.strip() if payload.client_name else None
    if "client_phone" in fields:
        booking.client_phone = payload.client_phone.strip() if payload.client_phone else None
    booking.updated_at = datetime.now(UTC)

    await session.flush()
    await log_activity(
        session,
        user.id,
        "viewing_booking",
        booking.id,
        "booking_updated",
        diff_payload(before, _booking_snapshot(booking)),
    )
    await session.commit()
    await session.refresh(booking)
    return await _booking_out(session, booking)


@bookings_router.post("/{booking_id}/cancel", response_model=ViewingBookingOut)
async def cancel_viewing_booking(
    booking_id: uuid.UUID,
    payload: ViewingBookingCancelIn | None = None,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.get(CrmViewingBooking, booking_id)
    before = _booking_snapshot(existing) if existing is not None else {}
    reason = payload.reason if payload is not None else None

    result, _ = await bot_bridge.cancel_viewing(
        session, booking_id=booking_id, reason=reason
    )
    if result != "cancelled":
        await session.rollback()
        _raise_for_fn_result(result)

    session.expire_all()
    booking = await session.get(CrmViewingBooking, booking_id)
    assert booking is not None
    diff = diff_payload(before, _booking_snapshot(booking))
    if reason:
        diff["reason"] = reason
    await log_activity(
        session,
        user.id,
        "viewing_booking",
        booking.id,
        "booking_cancelled",
        diff,
    )
    await session.commit()
    await session.refresh(booking)
    return await _booking_out(session, booking)


@bookings_router.post("/{booking_id}/reschedule", response_model=ViewingBookingOut)
async def reschedule_viewing_booking(
    booking_id: uuid.UUID,
    payload: ViewingBookingRescheduleIn,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.get(CrmViewingBooking, booking_id)
    before = _booking_snapshot(existing) if existing is not None else {}

    result, _ = await bot_bridge.reschedule_viewing(
        session, booking_id=booking_id, new_slot_id=payload.new_slot_id
    )
    if result != "rescheduled":
        await session.rollback()
        _raise_for_fn_result(result)

    session.expire_all()
    booking = await session.get(CrmViewingBooking, booking_id)
    assert booking is not None
    await log_activity(
        session,
        user.id,
        "viewing_booking",
        booking.id,
        "booking_rescheduled",
        diff_payload(before, _booking_snapshot(booking)),
    )
    await session.commit()
    await session.refresh(booking)
    return await _booking_out(session, booking)
