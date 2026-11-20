from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from backend.app.services.bot_bridge import book_viewing, cancel_viewing, reschedule_viewing
from backend.app.services.slots import build_slot_starts, generate_slots
from backend.app.workers.slots_worker import run_slots_cycle
from backend.tests.crm_helpers import engine_factory

pytestmark = pytest.mark.usefixtures("db_available", "migrated")

ET = ZoneInfo("America/New_York")


async def _insert_lead(
    session,
    wa: str,
    *,
    stage: str = "QUALIFIED",
    prev_stage: str | None = "NEW_INQUIRY",
    status: str = "ACTIVE",
    reminder_sent: bool = True,
) -> None:
    await session.execute(
        text(
            "INSERT INTO tcs_leads"
            " (whatsapp_id, name, current_stage, previous_stage, status, reminder_sent)"
            " VALUES (:wa, 'Viewing Test', :stage, :prev, :status, :rem)"
        ),
        {"wa": wa, "stage": stage, "prev": prev_stage, "status": status, "rem": reminder_sent},
    )


async def _insert_unit(session, building: str, unit_number: str) -> uuid.UUID:
    return (
        await session.execute(
            text(
                "INSERT INTO tcs_crm_units"
                " (building, unit_number, beds, baths, rent_usd, status)"
                " VALUES (:b, :u, 2, 1.5, 1950, 'available') RETURNING id"
            ),
            {"b": building, "u": unit_number},
        )
    ).scalar_one()


async def _insert_slot(
    session,
    starts_at: datetime,
    *,
    unit_id: uuid.UUID | None = None,
    status: str = "open",
) -> uuid.UUID:
    return (
        await session.execute(
            text(
                "INSERT INTO tcs_crm_viewing_slots (starts_at, duration_min, unit_id, status)"
                " VALUES (:starts_at, 60, :unit_id, :status) RETURNING id"
            ),
            {"starts_at": starts_at, "unit_id": unit_id, "status": status},
        )
    ).scalar_one()


async def test_book_cancel_reschedule_sync_lead_and_events(tx_session):
    wa = f"tg:vf_{uuid.uuid4().hex[:8]}"
    await _insert_lead(tx_session, wa, stage="QUALIFIED", prev_stage="NEW_INQUIRY", status="ACTIVE")
    unit_id = await _insert_unit(tx_session, "Tower North", f"N-{uuid.uuid4().hex[:4]}")
    s1_time = datetime.now(UTC) + timedelta(days=2)
    s2_time = datetime.now(UTC) + timedelta(days=3)
    slot1 = await _insert_slot(tx_session, s1_time)
    slot2 = await _insert_slot(tx_session, s2_time)

    # Book
    res, booking_id = await book_viewing(
        tx_session,
        whatsapp_id=wa,
        slot_id=slot1,
        unit_id=unit_id,
        client_name="Alice",
        client_phone="+12155550101",
    )
    assert res == "booked"
    assert booking_id is not None

    lead = (
        (
            await tx_session.execute(
                text(
                    "SELECT trial_datetime, current_stage, previous_stage, status,"
                    " reminder_sent, lead_data FROM tcs_leads WHERE whatsapp_id = :wa"
                ),
                {"wa": wa},
            )
        )
        .mappings()
        .one()
    )
    assert lead["trial_datetime"] == s1_time
    assert lead["current_stage"] == "VIEWING_SCHEDULED"
    assert lead["previous_stage"] == "QUALIFIED"
    assert lead["status"] == "VIEWING_BOOKED"
    assert lead["reminder_sent"] is False
    assert lead["lead_data"]["unit"].startswith("Tower North N-")

    # Reschedule
    await tx_session.execute(
        text("UPDATE tcs_leads SET reminder_sent = true WHERE whatsapp_id = :wa"), {"wa": wa}
    )
    res2, bid2 = await reschedule_viewing(tx_session, booking_id=booking_id, new_slot_id=slot2)
    assert res2 == "rescheduled"
    assert bid2 == booking_id

    s1_status = (
        await tx_session.execute(
            text("SELECT status FROM tcs_crm_viewing_slots WHERE id = :id"), {"id": slot1}
        )
    ).scalar_one()
    s2_status = (
        await tx_session.execute(
            text("SELECT status FROM tcs_crm_viewing_slots WHERE id = :id"), {"id": slot2}
        )
    ).scalar_one()
    assert s1_status == "open"
    assert s2_status == "booked"

    lead = (
        (
            await tx_session.execute(
                text(
                    "SELECT trial_datetime, current_stage, status, reminder_sent"
                    " FROM tcs_leads WHERE whatsapp_id = :wa"
                ),
                {"wa": wa},
            )
        )
        .mappings()
        .one()
    )
    assert lead["trial_datetime"] == s2_time
    assert lead["current_stage"] == "VIEWING_SCHEDULED"
    assert lead["status"] == "VIEWING_BOOKED"
    assert lead["reminder_sent"] is False

    # Cancel -> frees slot2 and reverts lead stage/status
    res3, _ = await cancel_viewing(tx_session, booking_id=booking_id, reason="busy")
    assert res3 == "cancelled"

    s2_status = (
        await tx_session.execute(
            text("SELECT status FROM tcs_crm_viewing_slots WHERE id = :id"), {"id": slot2}
        )
    ).scalar_one()
    assert s2_status == "open"

    lead = (
        (
            await tx_session.execute(
                text(
                    "SELECT trial_datetime, current_stage, status, reminder_sent"
                    " FROM tcs_leads WHERE whatsapp_id = :wa"
                ),
                {"wa": wa},
            )
        )
        .mappings()
        .one()
    )
    assert lead["trial_datetime"] is None
    assert lead["current_stage"] == "QUALIFIED"
    assert lead["status"] == "ACTIVE"
    assert lead["reminder_sent"] is False

    # Re-booking freed slot succeeds
    res4, booking_id2 = await book_viewing(
        tx_session,
        whatsapp_id=wa,
        slot_id=slot2,
        unit_id=unit_id,
        client_name="Alice",
        client_phone="+12155550101",
    )
    assert res4 == "booked"
    assert booking_id2 != booking_id

    events = (
        (
            await tx_session.execute(
                text(
                    "SELECT event_type FROM tcs_events"
                    " WHERE whatsapp_id = :wa ORDER BY id ASC"
                ),
                {"wa": wa},
            )
        )
        .scalars()
        .all()
    )
    assert events == ["trial_booked", "trial_rescheduled", "trial_cancelled", "trial_booked"]


async def test_book_lead_not_found_writes_nothing(tx_session):
    slot = await _insert_slot(tx_session, datetime.now(UTC) + timedelta(days=2))
    before_bookings = (
        await tx_session.execute(text("SELECT COUNT(*) FROM tcs_crm_viewing_bookings"))
    ).scalar_one()

    res, booking_id = await book_viewing(
        tx_session,
        whatsapp_id=f"tg:missing_{uuid.uuid4().hex[:8]}",
        slot_id=slot,
        client_name="Ghost",
    )
    assert res == "lead_not_found"
    assert booking_id is None

    slot_status = (
        await tx_session.execute(
            text("SELECT status FROM tcs_crm_viewing_slots WHERE id = :id"), {"id": slot}
        )
    ).scalar_one()
    after_bookings = (
        await tx_session.execute(text("SELECT COUNT(*) FROM tcs_crm_viewing_bookings"))
    ).scalar_one()
    assert slot_status == "open"
    assert after_bookings == before_bookings


async def test_rebooking_same_lead_cancels_previous_and_frees_slot(tx_session):
    wa = f"tg:rebook_{uuid.uuid4().hex[:8]}"
    await _insert_lead(tx_session, wa)
    slot1 = await _insert_slot(tx_session, datetime.now(UTC) + timedelta(days=2))
    slot2 = await _insert_slot(tx_session, datetime.now(UTC) + timedelta(days=3))

    res1, b1 = await book_viewing(tx_session, whatsapp_id=wa, slot_id=slot1, client_name="Bob")
    assert res1 == "booked" and b1 is not None

    res2, b2 = await book_viewing(tx_session, whatsapp_id=wa, slot_id=slot2, client_name="Bob")
    assert res2 == "booked" and b2 is not None and b2 != b1

    # Old slot is open again, new slot is booked
    statuses = dict(
        (
            await tx_session.execute(
                text(
                    "SELECT id, status FROM tcs_crm_viewing_slots WHERE id = ANY(:ids)"
                ),
                {"ids": [slot1, slot2]},
            )
        ).all()
    )
    assert statuses[slot1] == "open"
    assert statuses[slot2] == "booked"

    # Exactly one active booking for this lead
    active_ids = (
        (
            await tx_session.execute(
                text(
                    "SELECT id FROM tcs_crm_viewing_bookings"
                    " WHERE whatsapp_id = :wa AND status IN ('pending', 'confirmed')"
                ),
                {"wa": wa},
            )
        )
        .scalars()
        .all()
    )
    assert active_ids == [b2]

    old_status = (
        await tx_session.execute(
            text("SELECT status FROM tcs_crm_viewing_bookings WHERE id = :id"), {"id": b1}
        )
    ).scalar_one()
    assert old_status == "cancelled"

    events = (
        (
            await tx_session.execute(
                text("SELECT event_type FROM tcs_events WHERE whatsapp_id = :wa ORDER BY id ASC"),
                {"wa": wa},
            )
        )
        .scalars()
        .all()
    )
    assert events == ["trial_booked", "trial_rescheduled"]


async def test_blocked_slot_and_unit_mismatch_rejected(tx_session):
    wa = f"tg:block_{uuid.uuid4().hex[:8]}"
    await _insert_lead(tx_session, wa)
    unit_a = await _insert_unit(tx_session, "Block A", f"A-{uuid.uuid4().hex[:4]}")
    unit_b = await _insert_unit(tx_session, "Block B", f"B-{uuid.uuid4().hex[:4]}")

    blocked_slot = await _insert_slot(
        tx_session, datetime.now(UTC) + timedelta(days=2), status="blocked"
    )
    unit_a_slot = await _insert_slot(
        tx_session, datetime.now(UTC) + timedelta(days=2, hours=1), unit_id=unit_a
    )
    past_slot = await _insert_slot(tx_session, datetime.now(UTC) - timedelta(hours=1))

    res_blocked, b_blocked = await book_viewing(tx_session, whatsapp_id=wa, slot_id=blocked_slot)
    assert res_blocked == "slot_taken"
    assert b_blocked is None

    res_mismatch, b_mismatch = await book_viewing(
        tx_session, whatsapp_id=wa, slot_id=unit_a_slot, unit_id=unit_b
    )
    assert res_mismatch == "unit_mismatch"
    assert b_mismatch is None

    res_past, b_past = await book_viewing(tx_session, whatsapp_id=wa, slot_id=past_slot)
    assert res_past == "slot_in_past"
    assert b_past is None

    # Matching unit succeeds
    res_ok, b_ok = await book_viewing(
        tx_session, whatsapp_id=wa, slot_id=unit_a_slot, unit_id=unit_a
    )
    assert res_ok == "booked" and b_ok is not None


async def test_cancel_preserves_manual_deal_trial_at_when_different(tx_session):
    wa = f"tg:manual_{uuid.uuid4().hex[:8]}"
    await _insert_lead(tx_session, wa)
    pipeline_id = (
        await tx_session.execute(
            text("SELECT id FROM tcs_crm_pipelines ORDER BY is_default DESC, sort ASC LIMIT 1")
        )
    ).scalar_one()
    stage_id = (
        await tx_session.execute(
            text(
                "SELECT id FROM tcs_crm_stages"
                " WHERE pipeline_id = :pid AND kind = 'open' ORDER BY sort ASC LIMIT 1"
            ),
            {"pid": pipeline_id},
        )
    ).scalar_one()
    contact_id = (
        await tx_session.execute(
            text(
                "INSERT INTO tcs_crm_contacts (id, whatsapp_id, name)"
                " VALUES (:id, :wa, 'Manual Deal') RETURNING id"
            ),
            {"id": uuid.uuid4(), "wa": wa},
        )
    ).scalar_one()
    deal_id = (
        await tx_session.execute(
            text(
                "INSERT INTO tcs_crm_deals"
                " (id, contact_id, pipeline_id, stage_id, title, status)"
                " VALUES (:id, :cid, :pid, :sid, 'Manual Deal', 'open') RETURNING id"
            ),
            {"id": uuid.uuid4(), "cid": contact_id, "pid": pipeline_id, "sid": stage_id},
        )
    ).scalar_one()

    slot_time = datetime.now(UTC) + timedelta(days=2)
    slot_id = await _insert_slot(tx_session, slot_time)
    res, booking_id = await book_viewing(
        tx_session, whatsapp_id=wa, slot_id=slot_id, deal_id=deal_id, contact_id=contact_id
    )
    assert res == "booked" and booking_id is not None

    # Manager overrides deal.trial_at with a different manual datetime
    manual_time = datetime.now(UTC) + timedelta(days=5)
    await tx_session.execute(
        text("UPDATE tcs_crm_deals SET trial_at = :mt WHERE id = :id"),
        {"mt": manual_time, "id": deal_id},
    )

    res_cancel, _ = await cancel_viewing(tx_session, booking_id=booking_id, reason="test")
    assert res_cancel == "cancelled"

    deal_row = (
        (
            await tx_session.execute(
                text("SELECT trial_at, last_bot_trial_at FROM tcs_crm_deals WHERE id = :id"),
                {"id": deal_id},
            )
        )
        .mappings()
        .one()
    )
    # Manual trial_at is preserved, while last_bot_trial_at (which matched slot_time) is cleared
    assert deal_row["trial_at"] == manual_time
    assert deal_row["last_bot_trial_at"] is None


async def test_concurrent_booking_same_slot_only_one_wins(settings):
    engine, factory = engine_factory(settings)
    wa1 = f"tg:conc1_{uuid.uuid4().hex[:8]}"
    wa2 = f"tg:conc2_{uuid.uuid4().hex[:8]}"
    slot_id: uuid.UUID | None = None
    try:
        async with factory() as setup:
            await _insert_lead(setup, wa1)
            await _insert_lead(setup, wa2)
            slot_id = await _insert_slot(setup, datetime.now(UTC) + timedelta(days=4))
            await setup.commit()

        async def attempt(wa: str) -> str:
            async with factory() as s:
                res, _ = await book_viewing(s, whatsapp_id=wa, slot_id=slot_id)
                await s.commit()
                return res

        r1, r2 = await asyncio.gather(attempt(wa1), attempt(wa2))
        assert sorted([r1, r2]) == ["booked", "slot_taken"]

        async with factory() as verify:
            active_count = (
                await verify.execute(
                    text(
                        "SELECT COUNT(*) FROM tcs_crm_viewing_bookings"
                        " WHERE slot_id = :sid AND status IN ('pending', 'confirmed')"
                    ),
                    {"sid": slot_id},
                )
            ).scalar_one()
            assert active_count == 1
    finally:
        async with factory() as cleanup:
            if slot_id is not None:
                await cleanup.execute(
                    text("DELETE FROM tcs_crm_viewing_bookings WHERE slot_id = :sid"),
                    {"sid": slot_id},
                )
                await cleanup.execute(
                    text("DELETE FROM tcs_crm_viewing_slots WHERE id = :sid"),
                    {"sid": slot_id},
                )
            await cleanup.execute(
                text("DELETE FROM tcs_events WHERE whatsapp_id = ANY(:was)"), {"was": [wa1, wa2]}
            )
            await cleanup.execute(
                text("DELETE FROM tcs_leads WHERE whatsapp_id = ANY(:was)"), {"was": [wa1, wa2]}
            )
            await cleanup.commit()
        await engine.dispose()


def test_build_slot_starts_handles_dst_transitions():
    # Spring forward: 2026-03-08 02:00 ET -> 03:00 ET (EST UTC-5 -> EDT UTC-4)
    spring_now = datetime(2026, 3, 6, 12, 0, tzinfo=UTC)  # Fri 07:00 EST
    spring_slots = build_slot_starts(days=4, now=spring_now)
    fri_10 = [s for s in spring_slots if s.astimezone(ET).date().isoformat() == "2026-03-06"]
    mon_10 = [s for s in spring_slots if s.astimezone(ET).date().isoformat() == "2026-03-09"]
    assert len(fri_10) == 7
    assert len(mon_10) == 7
    # Fri 10:00 EST = 15:00 UTC; Mon 10:00 EDT = 14:00 UTC
    assert fri_10[0].hour == 15
    assert mon_10[0].hour == 14
    assert all(s.astimezone(ET).weekday() < 5 for s in spring_slots)

    # Fall back: 2026-11-01 02:00 ET -> 01:00 ET (EDT UTC-4 -> EST UTC-5)
    fall_now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)  # Fri 08:00 EDT
    fall_slots = build_slot_starts(days=4, now=fall_now)
    fri_fall = [s for s in fall_slots if s.astimezone(ET).date().isoformat() == "2026-10-30"]
    mon_fall = [s for s in fall_slots if s.astimezone(ET).date().isoformat() == "2026-11-02"]
    assert len(fri_fall) == 7
    assert len(mon_fall) == 7
    # Fri 10:00 EDT = 14:00 UTC; Mon 10:00 EST = 15:00 UTC
    assert fri_fall[0].hour == 14
    assert mon_fall[0].hour == 15


async def test_slots_generate_and_worker_idempotent(tx_session, settings):
    # Test service in tx_session with a far-future window to isolate from existing rows
    far_now = datetime(2030, 6, 3, 10, 0, tzinfo=UTC)  # Mon 06:00 EDT
    c1, total1 = await generate_slots(tx_session, days=4, now=far_now)
    assert c1 == total1 and c1 == 35  # Mon-Fri = 5 days * 7 slots
    c2, total2 = await generate_slots(tx_session, days=4, now=far_now)
    assert c2 == 0 and total2 == 35

    # Test daily worker cycle is idempotent
    engine, factory = engine_factory(settings)
    try:
        first = await run_slots_cycle(factory, days=14)
        second = await run_slots_cycle(factory, days=14)
        assert first is not None and first >= 0
        assert second == 0
    finally:
        await engine.dispose()
