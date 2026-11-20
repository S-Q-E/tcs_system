from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth_deps import CurrentUser, require_role, require_user
from ..deps import get_session, pagination
from ..errors import ApiError
from ..models import (
    ACTIVE_BOOKING_STATUSES,
    CrmImport,
    CrmUnit,
    CrmViewingBooking,
    CrmViewingSlot,
)
from ..schemas.contacts_data import ImportJobOut, ImportPreviewOut
from ..schemas.viewings import UnitCreate, UnitListOut, UnitOut, UnitUpdate
from ..services.activity import diff_payload, log_activity, slim
from ..services.importing import apply_unit_mapping, parse_csv_text
from .data_exchange import _decode_upload, _read_import_upload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/units", tags=["units"])
require_admin = require_role("admin")

_unit_import_tasks: set[asyncio.Task] = set()


def _unit_snapshot(unit: CrmUnit) -> dict:
    return slim(
        {
            "building": unit.building,
            "unit_number": unit.unit_number,
            "beds": unit.beds,
            "baths": float(unit.baths),
            "rent_usd": unit.rent_usd,
            "deposit_usd": unit.deposit_usd,
            "available_from": unit.available_from,
            "pets_policy": unit.pets_policy,
            "description": unit.description,
            "status": unit.status,
        }
    )


def _unit_out(unit: CrmUnit) -> UnitOut:
    return UnitOut.model_validate(unit)


@router.get("", response_model=UnitListOut)
async def list_units(
    status: str | None = Query(default=None, pattern="^(available|leased|hidden)$"),
    building: str | None = Query(default=None, max_length=255),
    beds: int | None = Query(default=None, ge=0, le=20),
    max_rent: int | None = Query(default=None, ge=0),
    search: str | None = Query(default=None, max_length=255),
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
    page: dict = Depends(pagination),
):
    del user
    stmt = select(CrmUnit).where(CrmUnit.deleted_at.is_(None))
    if status is not None:
        stmt = stmt.where(CrmUnit.status == status)
    if building:
        stmt = stmt.where(CrmUnit.building.ilike(f"%{building.strip()}%"))
    if beds is not None:
        stmt = stmt.where(CrmUnit.beds == beds)
    if max_rent is not None:
        stmt = stmt.where(CrmUnit.rent_usd <= max_rent)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                CrmUnit.building.ilike(term),
                CrmUnit.unit_number.ilike(term),
                CrmUnit.description.ilike(term),
                CrmUnit.pets_policy.ilike(term),
            )
        )
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (
        (
            await session.execute(
                stmt.order_by(CrmUnit.building.asc(), CrmUnit.unit_number.asc())
                .limit(page["limit"])
                .offset(page["offset"])
            )
        )
        .scalars()
        .all()
    )
    return UnitListOut(items=[_unit_out(u) for u in rows], total=int(total))


@router.get("/{unit_id}", response_model=UnitOut)
async def get_unit(
    unit_id: uuid.UUID,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    del user
    unit = await session.get(CrmUnit, unit_id)
    if unit is None or unit.deleted_at is not None:
        raise ApiError("NOT_FOUND", "Unit not found", 404)
    return _unit_out(unit)


@router.post("", response_model=UnitOut, status_code=201)
async def create_unit(
    payload: UnitCreate,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    unit = CrmUnit(
        building=payload.building.strip(),
        unit_number=payload.unit_number.strip(),
        beds=payload.beds,
        baths=Decimal(str(payload.baths)),
        rent_usd=payload.rent_usd,
        deposit_usd=payload.deposit_usd,
        available_from=payload.available_from,
        pets_policy=payload.pets_policy.strip() if payload.pets_policy else None,
        description=payload.description.strip() if payload.description else None,
        status=payload.status,
        photos=payload.photos,
    )
    session.add(unit)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(
            "UNIT_EXISTS", "A unit with this building and unit_number already exists", 409
        ) from exc
    await log_activity(
        session,
        admin.id,
        "unit",
        unit.id,
        "unit_created",
        diff_payload(None, _unit_snapshot(unit)),
    )
    await session.commit()
    await session.refresh(unit)
    return _unit_out(unit)


@router.patch("/{unit_id}", response_model=UnitOut)
async def update_unit(
    unit_id: uuid.UUID,
    payload: UnitUpdate,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    unit = await session.get(CrmUnit, unit_id)
    if unit is None or unit.deleted_at is not None:
        raise ApiError("NOT_FOUND", "Unit not found", 404)
    before = _unit_snapshot(unit)
    fields = payload.model_fields_set
    if "building" in fields and payload.building is not None:
        unit.building = payload.building.strip()
    if "unit_number" in fields and payload.unit_number is not None:
        unit.unit_number = payload.unit_number.strip()
    if "beds" in fields and payload.beds is not None:
        unit.beds = payload.beds
    if "baths" in fields and payload.baths is not None:
        unit.baths = Decimal(str(payload.baths))
    if "rent_usd" in fields and payload.rent_usd is not None:
        unit.rent_usd = payload.rent_usd
    if "deposit_usd" in fields:
        unit.deposit_usd = payload.deposit_usd
    if "available_from" in fields:
        unit.available_from = payload.available_from
    if "pets_policy" in fields:
        unit.pets_policy = payload.pets_policy.strip() if payload.pets_policy else None
    if "description" in fields:
        unit.description = payload.description.strip() if payload.description else None
    if "status" in fields and payload.status is not None:
        unit.status = payload.status
    if "photos" in fields and payload.photos is not None:
        unit.photos = payload.photos

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(
            "UNIT_EXISTS", "A unit with this building and unit_number already exists", 409
        ) from exc
    await log_activity(
        session,
        admin.id,
        "unit",
        unit.id,
        "unit_updated",
        diff_payload(before, _unit_snapshot(unit)),
    )
    await session.commit()
    await session.refresh(unit)
    return _unit_out(unit)


@router.delete("/{unit_id}")
async def delete_unit(
    unit_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    unit = await session.get(CrmUnit, unit_id)
    if unit is None or unit.deleted_at is not None:
        raise ApiError("NOT_FOUND", "Unit not found", 404)

    active_bookings = (
        await session.execute(
            select(func.count())
            .select_from(CrmViewingBooking)
            .outerjoin(CrmViewingSlot, CrmViewingSlot.id == CrmViewingBooking.slot_id)
            .where(
                CrmViewingBooking.status.in_(ACTIVE_BOOKING_STATUSES),
                or_(
                    CrmViewingBooking.unit_id == unit.id,
                    CrmViewingSlot.unit_id == unit.id,
                ),
            )
        )
    ).scalar() or 0
    if active_bookings > 0:
        raise ApiError(
            "UNIT_HAS_ACTIVE_BOOKINGS",
            "Cannot delete unit with active viewing bookings",
            409,
            {"active_bookings": int(active_bookings)},
        )

    before = _unit_snapshot(unit)
    unit.deleted_at = datetime.now(UTC)
    await log_activity(
        session,
        admin.id,
        "unit",
        unit.id,
        "unit_deleted",
        diff_payload(before, None),
    )
    await session.commit()
    return {"ok": True}


# ------------------------------------------------------------------ CSV import


@router.post("/import/preview", response_model=ImportPreviewOut)
async def units_import_preview(
    file: UploadFile = File(...),
    mapping: str = Form(default="{}"),
    admin: CurrentUser = Depends(require_admin),
):
    del admin
    try:
        mapping_dict = json.loads(mapping or "{}")
    except ValueError:
        raise ApiError("INVALID_MAPPING", "mapping must be JSON object", 422) from None
    if not isinstance(mapping_dict, dict):
        raise ApiError("INVALID_MAPPING", "mapping must be JSON object", 422)
    raw = await _read_import_upload(file)
    try:
        header, data = parse_csv_text(_decode_upload(raw))
    except ValueError as exc:
        raise ApiError("INVALID_CSV", str(exc), 422) from None
    records, errors = apply_unit_mapping(
        header, data, {str(k): str(v) for k, v in mapping_dict.items()}
    )
    return ImportPreviewOut(
        header=header,
        total=len(data),
        valid=len(records),
        invalid=len(errors),
        preview=records[:20],
        errors=errors[:50],
    )


def _start_unit_import_job(job_id: str, factory) -> None:
    task = asyncio.create_task(_run_unit_import_job(job_id, factory))
    _unit_import_tasks.add(task)
    task.add_done_callback(_unit_import_task_done)


def _unit_import_task_done(task: asyncio.Task) -> None:
    _unit_import_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("unit import task ended with an unexpected error", exc_info=task.exception())


@router.post("/import", response_model=ImportJobOut, status_code=201)
async def units_import_start(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(default="{}"),
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        mapping_dict = json.loads(mapping or "{}")
    except ValueError:
        raise ApiError("INVALID_MAPPING", "mapping must be JSON object", 422) from None
    if not isinstance(mapping_dict, dict):
        raise ApiError("INVALID_MAPPING", "mapping must be JSON object", 422)
    raw = await _read_import_upload(file)
    try:
        header, data = parse_csv_text(_decode_upload(raw))
    except ValueError as exc:
        raise ApiError("INVALID_CSV", str(exc), 422) from None
    job = CrmImport(
        entity="unit",
        status="queued",
        total=len(data),
        mapping={"mapping": mapping_dict, "header": header, "rows": data},
        errors=[],
        created_by=admin.id,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    await log_activity(
        session,
        admin.id,
        "import",
        job.id,
        "unit_import_queued",
        {"total": len(data)},
    )
    await session.commit()
    factory = request.app.state.session_factory
    _start_unit_import_job(str(job.id), factory)
    return ImportJobOut.model_validate(job)


@router.get("/import/{job_id}", response_model=ImportJobOut)
async def units_import_status(
    job_id: uuid.UUID,
    admin: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    del admin
    job = await session.get(CrmImport, job_id)
    if job is None or job.entity != "unit":
        raise ApiError("NOT_FOUND", "Import job not found", 404)
    return ImportJobOut.model_validate(job)


async def _run_unit_import_job(job_id: str, factory) -> None:
    try:
        await _execute_unit_import_job(job_id, factory)
    except Exception:
        logger.exception("unit import failed job_id=%s", job_id)
        async with factory() as session:
            job = await session.get(CrmImport, uuid.UUID(job_id))
            if job is not None and job.status not in ("done", "failed"):
                job.status = "failed"
                job.finished_at = datetime.now(UTC)
                job.errors = [{"error": "internal import error"}]
                await session.commit()


async def _execute_unit_import_job(job_id: str, factory) -> None:
    async with factory() as session:
        job = await session.get(CrmImport, uuid.UUID(job_id))
        if job is None or job.status != "queued":
            return
        job.status = "running"
        await session.commit()
        payload = job.mapping or {}
        header = payload.get("header", [])
        rows = payload.get("rows", [])
        mapping_dict = payload.get("mapping", {})
        str_mapping = {str(k): str(v) for k, v in mapping_dict.items()}
        records, pre_errors = apply_unit_mapping(header, rows, str_mapping)
        errors: list[dict] = list(pre_errors)
        ok = 0
        for idx, record in enumerate(records):
            try:
                avail = (
                    date.fromisoformat(record["available_from"])
                    if record.get("available_from")
                    else None
                )
                async with session.begin_nested():
                    unit = CrmUnit(
                        building=record["building"],
                        unit_number=record["unit_number"],
                        beds=record["beds"],
                        baths=Decimal(str(record["baths"])),
                        rent_usd=record["rent_usd"],
                        deposit_usd=record.get("deposit_usd"),
                        available_from=avail,
                        pets_policy=record.get("pets_policy"),
                        description=record.get("description"),
                        status=record.get("status") or "available",
                        photos=[],
                    )
                    session.add(unit)
                    await session.flush()
                ok += 1
            except IntegrityError:
                errors.append({"row": idx + 2, "error": "duplicate building + unit_number"})
            except Exception as exc:  # noqa: BLE001 - per-row report, never fail whole job
                errors.append({"row": idx + 2, "error": str(exc)})
        job.ok_count = ok
        job.error_count = len(errors)
        job.errors = errors[:200]
        job.status = "done"
        job.finished_at = datetime.now(UTC)
        await log_activity(
            session,
            job.created_by,
            "import",
            job.id,
            "unit_import_finished",
            {"ok": ok, "errors": len(errors)},
        )
        await session.commit()
