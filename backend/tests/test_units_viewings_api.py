from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from backend.tests.conftest import csrf_headers, login, login_admin, unique_email
from backend.tests.crm_helpers import engine_factory

pytestmark = pytest.mark.usefixtures("db_available", "migrated")


async def _create_manager(client, admin_csrf: str) -> tuple[str, str]:
    email = unique_email("mgr")
    password = "manager-pass-123"
    resp = await client.post(
        "/api/users",
        json={"email": email, "name": "Test Manager", "password": password, "role": "manager"},
        headers=csrf_headers(admin_csrf),
    )
    assert resp.status_code == 201, resp.text
    return email, password


async def _seed_lead(settings, wa: str) -> None:
    engine, factory = engine_factory(settings)
    try:
        async with factory() as s:
            await s.execute(
                text(
                    "INSERT INTO tcs_leads (whatsapp_id, name, current_stage, status)"
                    " VALUES (:wa, 'API Test Lead', 'QUALIFIED', 'ACTIVE')"
                    " ON CONFLICT (whatsapp_id) DO NOTHING"
                ),
                {"wa": wa},
            )
            await s.commit()
    finally:
        await engine.dispose()


async def _cleanup_lead(settings, wa: str) -> None:
    engine, factory = engine_factory(settings)
    try:
        async with factory() as s:
            await s.execute(
                text("DELETE FROM tcs_crm_viewing_bookings WHERE whatsapp_id = :wa"), {"wa": wa}
            )
            await s.execute(text("DELETE FROM tcs_events WHERE whatsapp_id = :wa"), {"wa": wa})
            await s.execute(text("DELETE FROM tcs_leads WHERE whatsapp_id = :wa"), {"wa": wa})
            await s.commit()
    finally:
        await engine.dispose()


async def test_units_crud_duplicate_soft_delete_and_activity_log(client, settings):
    admin = await login_admin(client, settings)
    headers = csrf_headers(admin["csrf"])
    tag = uuid.uuid4().hex[:6]
    building = f"Maple Lofts {tag}"

    # Create
    resp = await client.post(
        "/api/units",
        json={
            "building": building,
            "unit_number": "101",
            "beds": 2,
            "baths": 1.5,
            "rent_usd": 2100,
            "deposit_usd": 2100,
            "pets_policy": "Cats allowed",
            "status": "available",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    unit = resp.json()
    unit_id = unit["id"]
    assert unit["building"] == building
    assert unit["status"] == "available"

    # Duplicate -> 409 UNIT_EXISTS
    dup = await client.post(
        "/api/units",
        json={
            "building": building,
            "unit_number": "101",
            "beds": 2,
            "baths": 1.5,
            "rent_usd": 2100,
        },
        headers=headers,
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "UNIT_EXISTS"

    # Filter & list
    listed = await client.get(f"/api/units?building={building}&status=available&beds=2&max_rent=2200")
    assert listed.status_code == 200
    assert any(u["id"] == unit_id for u in listed.json()["items"])

    # Patch status + rent
    patched = await client.patch(
        f"/api/units/{unit_id}",
        json={"status": "leased", "rent_usd": 2250},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "leased"
    assert patched.json()["rent_usd"] == 2250

    # Soft delete
    deleted = await client.delete(f"/api/units/{unit_id}", headers=headers)
    assert deleted.status_code == 200
    assert (await client.get(f"/api/units/{unit_id}")).status_code == 404

    # Activity log entries recorded with old/new values
    engine, factory = engine_factory(settings)
    try:
        async with factory() as s:
            rows = (
                (
                    await s.execute(
                        text(
                            "SELECT action, diff FROM tcs_crm_activity_log"
                            " WHERE entity = 'unit' AND entity_id = :id ORDER BY created_at ASC"
                        ),
                        {"id": uuid.UUID(unit_id)},
                    )
                )
                .mappings()
                .all()
            )
            actions = [r["action"] for r in rows]
            assert actions == ["unit_created", "unit_updated", "unit_deleted"]
            assert rows[1]["diff"]["changed"]["status"] == {"old": "available", "new": "leased"}
    finally:
        await engine.dispose()


async def test_delete_unit_with_active_booking_forbidden(client, settings):
    admin = await login_admin(client, settings)
    headers = csrf_headers(admin["csrf"])
    wa = f"tg:api_del_{uuid.uuid4().hex[:8]}"
    await _seed_lead(settings, wa)

    slot_id = None
    unit_id = None
    try:
        unit_resp = await client.post(
            "/api/units",
            json={
                "building": f"DelGuard {uuid.uuid4().hex[:6]}",
                "unit_number": "201",
                "beds": 1,
                "baths": 1,
                "rent_usd": 1700,
            },
            headers=headers,
        )
        assert unit_resp.status_code == 201
        unit_id = unit_resp.json()["id"]

        starts = (datetime.now(UTC) + timedelta(days=20, hours=3)).replace(
            minute=0, second=0, microsecond=0
        )
        slot_resp = await client.post(
            "/api/viewing-slots",
            json={"starts_at": starts.isoformat(), "duration_min": 60, "unit_id": unit_id},
            headers=headers,
        )
        assert slot_resp.status_code == 201
        slot_id = slot_resp.json()["id"]

        book_resp = await client.post(
            "/api/viewing-bookings",
            json={
                "slot_id": slot_id,
                "unit_id": unit_id,
                "whatsapp_id": wa,
                "client_name": "Guard Test",
            },
            headers=headers,
        )
        assert book_resp.status_code == 201, book_resp.text
        booking_id = book_resp.json()["id"]

        # Deleting unit with active booking is blocked
        del_blocked = await client.delete(f"/api/units/{unit_id}", headers=headers)
        assert del_blocked.status_code == 409
        assert del_blocked.json()["error"]["code"] == "UNIT_HAS_ACTIVE_BOOKINGS"

        # After cancel, deleting unit succeeds
        cancel_resp = await client.post(
            f"/api/viewing-bookings/{booking_id}/cancel",
            json={"reason": "released"},
            headers=headers,
        )
        assert cancel_resp.status_code == 200
        del_ok = await client.delete(f"/api/units/{unit_id}", headers=headers)
        assert del_ok.status_code == 200
    finally:
        await _cleanup_lead(settings, wa)
        if slot_id:
            engine, factory = engine_factory(settings)
            try:
                async with factory() as s:
                    await s.execute(
                        text("DELETE FROM tcs_crm_viewing_slots WHERE id = :id"),
                        {"id": uuid.UUID(slot_id)},
                    )
                    await s.commit()
            finally:
                await engine.dispose()


async def test_slots_bookings_errors_and_manager_permissions(client, settings):
    admin = await login_admin(client, settings)
    admin_headers = csrf_headers(admin["csrf"])
    mgr_email, mgr_pass = await _create_manager(client, admin["csrf"])

    # Past slot -> 400 SLOT_IN_PAST
    past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    past_resp = await client.post(
        "/api/viewing-slots", json={"starts_at": past}, headers=admin_headers
    )
    assert past_resp.status_code == 400
    assert past_resp.json()["error"]["code"] == "SLOT_IN_PAST"

    # Generate slots idempotently
    gen1 = await client.post(
        "/api/viewing-slots/generate", json={"days": 14}, headers=admin_headers
    )
    assert gen1.status_code == 200
    gen2 = await client.post(
        "/api/viewing-slots/generate", json={"days": 14}, headers=admin_headers
    )
    assert gen2.status_code == 200
    assert gen2.json()["created"] == 0

    # Create two dedicated future slots
    t1 = (datetime.now(UTC) + timedelta(days=25, hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    t2 = t1 + timedelta(hours=1)
    s1 = (
        await client.post(
            "/api/viewing-slots", json={"starts_at": t1.isoformat()}, headers=admin_headers
        )
    ).json()
    s2 = (
        await client.post(
            "/api/viewing-slots", json={"starts_at": t2.isoformat()}, headers=admin_headers
        )
    ).json()

    # Duplicate slot -> 409 SLOT_TAKEN
    dup_slot = await client.post(
        "/api/viewing-slots", json={"starts_at": t1.isoformat()}, headers=admin_headers
    )
    assert dup_slot.status_code == 409
    assert dup_slot.json()["error"]["code"] == "SLOT_TAKEN"

    # Log in as manager
    mgr = await login(client, mgr_email, mgr_pass)
    mgr_headers = csrf_headers(mgr["csrf"])

    # Manager CANNOT modify units or slots
    assert (
        await client.post(
            "/api/units",
            json={"building": "Nope", "unit_number": "1", "beds": 1, "baths": 1, "rent_usd": 1000},
            headers=mgr_headers,
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/viewing-slots", json={"starts_at": (t2 + timedelta(hours=1)).isoformat()}, headers=mgr_headers
        )
    ).status_code == 403
    assert (
        await client.post("/api/viewing-slots/generate", json={"days": 7}, headers=mgr_headers)
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/viewing-slots/{s1['id']}", json={"status": "blocked"}, headers=mgr_headers
        )
    ).status_code == 403
    assert (
        await client.delete(f"/api/viewing-slots/{s1['id']}", headers=mgr_headers)
    ).status_code == 403

    # Manager CAN read units & slots, and book/reschedule/cancel bookings
    assert (await client.get("/api/units")).status_code == 200
    assert (await client.get("/api/viewing-slots")).status_code == 200

    wa = f"tg:mgr_book_{uuid.uuid4().hex[:8]}"
    await _seed_lead(settings, wa)
    try:
        b = await client.post(
            "/api/viewing-bookings",
            json={"slot_id": s1["id"], "whatsapp_id": wa, "client_name": "Mgr Client"},
            headers=mgr_headers,
        )
        assert b.status_code == 201, b.text
        booking_id = b.json()["id"]

        # Booking the same taken slot -> 409 SLOT_TAKEN
        wa2 = f"tg:mgr_book2_{uuid.uuid4().hex[:8]}"
        await _seed_lead(settings, wa2)
        try:
            taken = await client.post(
                "/api/viewing-bookings",
                json={"slot_id": s1["id"], "whatsapp_id": wa2, "client_name": "Second"},
                headers=mgr_headers,
            )
            assert taken.status_code == 409
            assert taken.json()["error"]["code"] == "SLOT_TAKEN"
        finally:
            await _cleanup_lead(settings, wa2)

        # Manager reschedules to s2
        resch = await client.post(
            f"/api/viewing-bookings/{booking_id}/reschedule",
            json={"new_slot_id": s2["id"]},
            headers=mgr_headers,
        )
        assert resch.status_code == 200, resch.text
        assert resch.json()["slot_id"] == s2["id"]

        # Manager updates notes
        upd = await client.patch(
            f"/api/viewing-bookings/{booking_id}",
            json={"notes": "Bringing roommate"},
            headers=mgr_headers,
        )
        assert upd.status_code == 200
        assert upd.json()["notes"] == "Bringing roommate"

        # Manager cancels
        canc = await client.post(
            f"/api/viewing-bookings/{booking_id}/cancel",
            json={"reason": "rescheduling later"},
            headers=mgr_headers,
        )
        assert canc.status_code == 200
        assert canc.json()["status"] == "cancelled"
    finally:
        await _cleanup_lead(settings, wa)
        engine, factory = engine_factory(settings)
        try:
            async with factory() as s:
                await s.execute(
                    text("DELETE FROM tcs_crm_viewing_slots WHERE id = ANY(:ids)"),
                    {"ids": [uuid.UUID(s1["id"]), uuid.UUID(s2["id"])]},
                )
                await s.commit()
        finally:
            await engine.dispose()


async def test_units_csv_import(client, settings):
    admin = await login_admin(client, settings)
    headers = csrf_headers(admin["csrf"])
    tag = uuid.uuid4().hex[:6]
    csv_body = (
        "building,unit_number,beds,baths,rent_usd,deposit_usd,status\n"
        f"CSV Tower {tag},A-1,1,1,1600,1600,available\n"
        f"CSV Tower {tag},A-2,2,2,2300,2300,leased\n"
        f"CSV Tower {tag},BAD,notanint,1,1500,1500,available\n"
    )
    mapping = json.dumps(
        {
            "building": "building",
            "unit_number": "unit_number",
            "beds": "beds",
            "baths": "baths",
            "rent_usd": "rent_usd",
            "deposit_usd": "deposit_usd",
            "status": "status",
        }
    )

    prev = await client.post(
        "/api/units/import/preview",
        files={"file": ("units.csv", csv_body.encode(), "text/csv")},
        data={"mapping": mapping},
        headers=headers,
    )
    assert prev.status_code == 200, prev.text
    assert prev.json()["valid"] == 2
    assert prev.json()["invalid"] == 1

    start = await client.post(
        "/api/units/import",
        files={"file": ("units.csv", csv_body.encode(), "text/csv")},
        data={"mapping": mapping},
        headers=headers,
    )
    assert start.status_code == 201, start.text
    job_id = start.json()["id"]

    job = None
    for _ in range(30):
        st = await client.get(f"/api/units/import/{job_id}")
        assert st.status_code == 200
        job = st.json()
        if job["status"] in ("done", "failed"):
            break
        await asyncio.sleep(0.05)
    assert job is not None and job["status"] == "done"
    assert job["ok_count"] == 2
    assert job["error_count"] == 1
