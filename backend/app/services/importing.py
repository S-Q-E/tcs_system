from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

CONTACT_IMPORTABLE = ("name", "phone", "email", "whatsapp_id", "source")
UNIT_IMPORTABLE = (
    "building",
    "unit_number",
    "beds",
    "baths",
    "rent_usd",
    "deposit_usd",
    "available_from",
    "pets_policy",
    "description",
    "status",
)
VALID_UNIT_IMPORT_STATUSES = ("available", "leased", "hidden")


def parse_csv_text(text: str, max_rows: int = 2000) -> tuple[list[str], list[list[str]]]:
    sample = text[:100000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("empty csv")
    header, data = rows[0], rows[1:]
    if len(data) > max_rows:
        raise ValueError(f"too many rows (max {max_rows})")
    return [h.strip() for h in header], data


def apply_mapping(
    header: list[str], rows: list[list[str]], mapping: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Map CSV columns to contact fields. Returns (records, row_errors)."""
    records: list[dict] = []
    errors: list[dict] = []
    for idx, row in enumerate(rows, start=2):
        record: dict[str, str | None] = {}
        padded = row + [""] * (len(header) - len(row))
        for col, field in mapping.items():
            if field in (None, "", "ignore"):
                continue
            if field not in CONTACT_IMPORTABLE:
                errors.append({"row": idx, "error": f"unknown field {field}"})
                record = {}
                break
            try:
                pos = header.index(col)
            except ValueError:
                errors.append({"row": idx, "error": f"unknown column {col}"})
                record = {}
                break
            record[field] = padded[pos].strip() or None
        else:
            err = validate_record(record, idx)
            if err:
                errors.append(err)
            else:
                records.append(record)
            continue
        continue
    return records, errors


def validate_record(record: dict, row_no: int) -> dict | None:
    if not any(record.get(k) for k in ("name", "phone", "email", "whatsapp_id")):
        return {"row": row_no, "error": "empty row: need name, phone, email or whatsapp_id"}
    if record.get("email") and "@" not in str(record["email"]):
        return {"row": row_no, "error": "invalid email"}
    return None


def preview_from_text(text: str, mapping: dict[str, str], limit: int = 20) -> dict:
    header, data = parse_csv_text(text)
    records, errors = apply_mapping(header, data, mapping)
    return {
        "header": header,
        "total": len(data),
        "valid": len(records),
        "invalid": len(errors),
        "preview": records[:limit],
        "errors": errors[:50],
    }


def new_job_id() -> uuid.UUID:
    return uuid.uuid4()


def apply_unit_mapping(
    header: list[str], rows: list[list[str]], mapping: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Map CSV columns to unit fields. Returns (records, row_errors)."""
    records: list[dict] = []
    errors: list[dict] = []
    for idx, row in enumerate(rows, start=2):
        raw: dict[str, str | None] = {}
        padded = row + [""] * (len(header) - len(row))
        for col, field in mapping.items():
            if field in (None, "", "ignore"):
                continue
            if field not in UNIT_IMPORTABLE:
                errors.append({"row": idx, "error": f"unknown field {field}"})
                raw = {}
                break
            try:
                pos = header.index(col)
            except ValueError:
                errors.append({"row": idx, "error": f"unknown column {col}"})
                raw = {}
                break
            raw[field] = padded[pos].strip() or None
        else:
            parsed, err = validate_unit_record(raw, idx)
            if err:
                errors.append(err)
            elif parsed is not None:
                records.append(parsed)
            continue
        continue
    return records, errors


def validate_unit_record(raw: dict[str, str | None], row_no: int) -> tuple[dict | None, dict | None]:
    building = (raw.get("building") or "").strip()
    unit_number = (raw.get("unit_number") or "").strip()
    if not building or not unit_number:
        return None, {"row": row_no, "error": "building and unit_number are required"}

    try:
        beds = int(raw["beds"]) if raw.get("beds") is not None else -1
    except ValueError:
        return None, {"row": row_no, "error": "beds must be an integer"}
    if beds < 0 or beds > 20:
        return None, {"row": row_no, "error": "beds must be between 0 and 20"}

    try:
        baths = Decimal(raw["baths"]) if raw.get("baths") is not None else Decimal("-1")
    except InvalidOperation:
        return None, {"row": row_no, "error": "baths must be a number"}
    if baths <= 0 or baths > 20:
        return None, {"row": row_no, "error": "baths must be > 0 and <= 20"}

    try:
        rent_str = (raw.get("rent_usd") or "").replace("$", "").replace(",", "")
        rent_usd = int(rent_str) if rent_str else -1
    except ValueError:
        return None, {"row": row_no, "error": "rent_usd must be an integer"}
    if rent_usd < 0:
        return None, {"row": row_no, "error": "rent_usd must be >= 0"}

    deposit_usd: int | None = None
    if raw.get("deposit_usd"):
        try:
            dep_str = raw["deposit_usd"].replace("$", "").replace(",", "")
            deposit_usd = int(dep_str)
        except ValueError:
            return None, {"row": row_no, "error": "deposit_usd must be an integer"}
        if deposit_usd < 0:
            return None, {"row": row_no, "error": "deposit_usd must be >= 0"}

    available_from: str | None = None
    if raw.get("available_from"):
        try:
            available_from = date.fromisoformat(raw["available_from"]).isoformat()
        except ValueError:
            return None, {"row": row_no, "error": "available_from must be YYYY-MM-DD"}

    status = (raw.get("status") or "available").lower()
    if status not in VALID_UNIT_IMPORT_STATUSES:
        return None, {
            "row": row_no,
            "error": f"invalid status {status!r} (expected available, leased, or hidden)",
        }

    return (
        {
            "building": building,
            "unit_number": unit_number,
            "beds": beds,
            "baths": float(baths),
            "rent_usd": rent_usd,
            "deposit_usd": deposit_usd,
            "available_from": available_from,
            "pets_policy": raw.get("pets_policy"),
            "description": raw.get("description"),
            "status": status,
        },
        None,
    )
