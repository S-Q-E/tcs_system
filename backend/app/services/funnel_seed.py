from __future__ import annotations

import uuid

from sqlalchemy import text

DEFAULT_PIPELINE_NAME = "TCS Leasing"

# Exactly six stages; all of them are board columns, including won/lost.
# (name, color, kind, bot_stage_key, bot_status_key) in board order.
# Meaning for the bot:
#   NEW_INQUIRY       - only the first message
#   QUALIFIED         - bedrooms or unit known AND move-in date or budget known
#   VIEWING_SCHEDULED - a viewing is booked (trial_datetime is set)
#   VIEWING_DONE      - the viewing happened (a manager moves the card)
#   LEASED / LOST     - terminal, matched by the lead status
STAGES: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    ("New inquiry", "#38BDF8", "open", "NEW_INQUIRY", None),
    ("Qualified", "#818CF8", "open", "QUALIFIED", None),
    ("Viewing scheduled", "#FBBF24", "open", "VIEWING_SCHEDULED", None),
    ("Viewing done", "#34D399", "open", "VIEWING_DONE", None),
    ("Leased", "#16A34A", "won", None, "LEASED"),
    ("Lost", "#EF4444", "lost", None, "LOST"),
)

LOST_REASONS: tuple[str, ...] = (
    "Price too high",
    "Found another place",
    "Not responding",
    "Bad timing",
    "Other",
)


def seed_default_funnel(conn) -> uuid.UUID:
    """Insert the single default pipeline, its stages, and lost reasons if missing.

    Idempotent: existing rows (matched by name) are left untouched.
    Works with any sync SQLAlchemy connection (Alembic migrations, run_sync).
    Returns the default pipeline id.
    """
    pipeline_id = conn.execute(
        text("SELECT id FROM tcs_crm_pipelines WHERE name = :name"),
        {"name": DEFAULT_PIPELINE_NAME},
    ).scalar_one_or_none()
    if pipeline_id is None:
        pipeline_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO tcs_crm_pipelines (id, name, is_default, sort)"
                " VALUES (:id, :name, TRUE, 0)"
            ),
            {"id": str(pipeline_id), "name": DEFAULT_PIPELINE_NAME},
        )

    for sort, (name, color, kind, stage_key, status_key) in enumerate(STAGES):
        exists = conn.execute(
            text(
                "SELECT id FROM tcs_crm_stages" " WHERE pipeline_id = :pipeline_id AND name = :name"
            ),
            {"pipeline_id": str(pipeline_id), "name": name},
        ).scalar_one_or_none()
        if exists is None:
            conn.execute(
                text(
                    "INSERT INTO tcs_crm_stages"
                    " (id, pipeline_id, name, color, sort, kind, bot_stage_key, bot_status_key)"
                    " VALUES (:id, :pipeline_id, :name, :color, :sort,"
                    " :kind, :stage_key, :status_key)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "pipeline_id": str(pipeline_id),
                    "name": name,
                    "color": color,
                    "sort": sort,
                    "kind": kind,
                    "stage_key": stage_key,
                    "status_key": status_key,
                },
            )

    for sort, name in enumerate(LOST_REASONS):
        exists = conn.execute(
            text("SELECT id FROM tcs_crm_lost_reasons WHERE name = :name"), {"name": name}
        ).scalar_one_or_none()
        if exists is None:
            conn.execute(
                text(
                    "INSERT INTO tcs_crm_lost_reasons (id, name, sort)"
                    " VALUES (:id, :name, :sort)"
                ),
                {"id": str(uuid.uuid4()), "name": name, "sort": sort},
            )
    return pipeline_id
