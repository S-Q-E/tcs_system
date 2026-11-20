"""Units, viewing slots, viewing bookings and atomic booking functions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_units_slots_bookings"
down_revision = "0022_sync_contact_fields"
branch_labels = None
depends_on = None

ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _ts(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.func.now() if not nullable else None,
    )


BOOK_VIEWING_FN = """
CREATE OR REPLACE FUNCTION tcs_crm_book_viewing(
    p_whatsapp_id TEXT,
    p_slot_id UUID,
    p_unit_id UUID DEFAULT NULL,
    p_client_name TEXT DEFAULT NULL,
    p_client_phone TEXT DEFAULT NULL,
    p_deal_id UUID DEFAULT NULL,
    p_contact_id UUID DEFAULT NULL,
    p_notes TEXT DEFAULT NULL,
    p_created_by UUID DEFAULT NULL
)
RETURNS TABLE(result TEXT, booking_id UUID)
LANGUAGE plpgsql
AS $$
DECLARE
    v_slot RECORD;
    v_unit RECORD;
    v_lead RECORD;
    v_old_booking RECORD;
    v_booking_id UUID;
    v_eff_unit_id UUID;
    v_eff_contact_id UUID := p_contact_id;
    v_eff_deal_id UUID := p_deal_id;
    v_eff_whatsapp_id TEXT := NULLIF(BTRIM(p_whatsapp_id), '');
    v_unit_label TEXT;
    v_building TEXT;
    v_unit_number TEXT;
    v_prev_stage TEXT;
    v_replaced BOOLEAN := FALSE;
    v_old_slot_id UUID;
    v_old_starts_at TIMESTAMPTZ;
    v_old_booking_id UUID;
BEGIN
    IF v_eff_deal_id IS NOT NULL AND v_eff_contact_id IS NULL THEN
        SELECT contact_id INTO v_eff_contact_id
          FROM tcs_crm_deals
         WHERE id = v_eff_deal_id;
    END IF;

    IF v_eff_whatsapp_id IS NULL AND v_eff_contact_id IS NOT NULL THEN
        SELECT NULLIF(BTRIM(whatsapp_id), '') INTO v_eff_whatsapp_id
          FROM tcs_crm_contacts
         WHERE id = v_eff_contact_id;
    END IF;

    -- When whatsapp_id is present, the lead MUST exist in tcs_leads; write nothing otherwise.
    IF v_eff_whatsapp_id IS NOT NULL THEN
        IF to_regclass('public.tcs_leads') IS NULL THEN
            RETURN QUERY SELECT 'lead_not_found'::TEXT, NULL::UUID;
            RETURN;
        END IF;

        SELECT current_stage, previous_stage, status
          INTO v_lead
          FROM tcs_leads
         WHERE whatsapp_id = v_eff_whatsapp_id
           FOR UPDATE;

        IF NOT FOUND THEN
            RETURN QUERY SELECT 'lead_not_found'::TEXT, NULL::UUID;
            RETURN;
        END IF;
    END IF;

    -- Lock target slot row to serialize concurrent bookings on the same slot.
    SELECT id, starts_at, duration_min, unit_id, status
      INTO v_slot
      FROM tcs_crm_viewing_slots
     WHERE id = p_slot_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'slot_not_found'::TEXT, NULL::UUID;
        RETURN;
    END IF;

    IF v_slot.starts_at <= now() THEN
        RETURN QUERY SELECT 'slot_in_past'::TEXT, NULL::UUID;
        RETURN;
    END IF;

    IF v_slot.status <> 'open' THEN
        RETURN QUERY SELECT 'slot_taken'::TEXT, NULL::UUID;
        RETURN;
    END IF;

    IF v_slot.unit_id IS NOT NULL AND p_unit_id IS NOT NULL AND v_slot.unit_id <> p_unit_id THEN
        RETURN QUERY SELECT 'unit_mismatch'::TEXT, NULL::UUID;
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM tcs_crm_viewing_bookings
         WHERE slot_id = p_slot_id
           AND status IN ('pending', 'confirmed')
    ) THEN
        RETURN QUERY SELECT 'slot_taken'::TEXT, NULL::UUID;
        RETURN;
    END IF;

    v_eff_unit_id := COALESCE(p_unit_id, v_slot.unit_id);

    IF v_eff_unit_id IS NOT NULL THEN
        SELECT building, unit_number
          INTO v_unit
          FROM tcs_crm_units
         WHERE id = v_eff_unit_id
           AND deleted_at IS NULL;
        IF FOUND THEN
            v_building := v_unit.building;
            v_unit_number := v_unit.unit_number;
            v_unit_label := v_unit.building || ' ' || v_unit.unit_number;
        END IF;
    END IF;

    IF v_eff_contact_id IS NULL AND v_eff_whatsapp_id IS NOT NULL THEN
        SELECT id INTO v_eff_contact_id
          FROM tcs_crm_contacts
         WHERE whatsapp_id = v_eff_whatsapp_id
           AND deleted_at IS NULL
         LIMIT 1;
    END IF;

    IF v_eff_deal_id IS NULL AND v_eff_contact_id IS NOT NULL THEN
        SELECT id INTO v_eff_deal_id
          FROM tcs_crm_deals
         WHERE contact_id = v_eff_contact_id
           AND deleted_at IS NULL
         ORDER BY updated_at DESC, id
         LIMIT 1;
    END IF;

    -- If this lead (or deal when no whatsapp_id) already has active booking(s),
    -- cancel them and free their slot(s) atomically in this same transaction.
    FOR v_old_booking IN
        SELECT b.id, b.slot_id, s.starts_at
          FROM tcs_crm_viewing_bookings b
          JOIN tcs_crm_viewing_slots s ON s.id = b.slot_id
         WHERE b.status IN ('pending', 'confirmed')
           AND (
               (v_eff_whatsapp_id IS NOT NULL AND b.whatsapp_id = v_eff_whatsapp_id)
               OR (v_eff_whatsapp_id IS NULL AND v_eff_deal_id IS NOT NULL AND b.deal_id = v_eff_deal_id)
           )
         ORDER BY b.created_at DESC
           FOR UPDATE OF b
    LOOP
        UPDATE tcs_crm_viewing_bookings
           SET status = 'cancelled',
               cancelled_at = now(),
               updated_at = now()
         WHERE id = v_old_booking.id;

        UPDATE tcs_crm_viewing_slots
           SET status = 'open'
         WHERE id = v_old_booking.slot_id
           AND status = 'booked';

        IF NOT v_replaced THEN
            v_replaced := TRUE;
            v_old_booking_id := v_old_booking.id;
            v_old_slot_id := v_old_booking.slot_id;
            v_old_starts_at := v_old_booking.starts_at;
        END IF;
    END LOOP;

    BEGIN
        INSERT INTO tcs_crm_viewing_bookings (
            slot_id,
            unit_id,
            deal_id,
            contact_id,
            whatsapp_id,
            client_name,
            client_phone,
            status,
            notes,
            created_by
        )
        VALUES (
            p_slot_id,
            v_eff_unit_id,
            v_eff_deal_id,
            v_eff_contact_id,
            v_eff_whatsapp_id,
            NULLIF(BTRIM(p_client_name), ''),
            NULLIF(BTRIM(p_client_phone), ''),
            'confirmed',
            p_notes,
            p_created_by
        )
        RETURNING id INTO v_booking_id;
    EXCEPTION
        WHEN unique_violation THEN
            RETURN QUERY SELECT 'slot_taken'::TEXT, NULL::UUID;
            RETURN;
    END;

    UPDATE tcs_crm_viewing_slots
       SET status = 'booked'
     WHERE id = p_slot_id;

    IF v_eff_whatsapp_id IS NOT NULL THEN
        v_prev_stage := v_lead.current_stage;
        UPDATE tcs_leads
           SET trial_datetime = v_slot.starts_at,
               previous_stage = CASE
                   WHEN current_stage IS DISTINCT FROM 'VIEWING_SCHEDULED'
                   THEN current_stage
                   ELSE previous_stage
               END,
               current_stage = 'VIEWING_SCHEDULED',
               status = 'VIEWING_BOOKED',
               reminder_sent = false,
               lead_data = CASE
                   WHEN v_unit_label IS NOT NULL
                   THEN COALESCE(lead_data, '{}'::jsonb)
                        || jsonb_build_object('unit', v_unit_label)
                   ELSE lead_data
               END,
               last_message_at = now(),
               updated_at = now()
         WHERE whatsapp_id = v_eff_whatsapp_id;

        IF to_regclass('public.tcs_events') IS NOT NULL THEN
            IF v_replaced THEN
                INSERT INTO tcs_events (
                    whatsapp_id,
                    event_type,
                    from_stage,
                    to_stage,
                    payload,
                    created_at
                )
                VALUES (
                    v_eff_whatsapp_id,
                    'trial_rescheduled',
                    v_prev_stage,
                    'VIEWING_SCHEDULED',
                    jsonb_build_object(
                        'booking_id', v_booking_id,
                        'previous_booking_id', v_old_booking_id,
                        'old_slot_id', v_old_slot_id,
                        'new_slot_id', p_slot_id,
                        'old_trial_datetime', v_old_starts_at,
                        'trial_datetime', v_slot.starts_at,
                        'unit_id', v_eff_unit_id,
                        'building', v_building,
                        'unit_number', v_unit_number
                    ),
                    now()
                );
            ELSE
                INSERT INTO tcs_events (
                    whatsapp_id,
                    event_type,
                    from_stage,
                    to_stage,
                    payload,
                    created_at
                )
                VALUES (
                    v_eff_whatsapp_id,
                    'trial_booked',
                    v_prev_stage,
                    'VIEWING_SCHEDULED',
                    jsonb_build_object(
                        'booking_id', v_booking_id,
                        'slot_id', p_slot_id,
                        'trial_datetime', v_slot.starts_at,
                        'unit_id', v_eff_unit_id,
                        'building', v_building,
                        'unit_number', v_unit_number
                    ),
                    now()
                );
            END IF;
        END IF;
    END IF;

    IF v_eff_deal_id IS NOT NULL THEN
        UPDATE tcs_crm_deals
           SET trial_at = v_slot.starts_at,
               last_bot_trial_at = v_slot.starts_at,
               updated_at = now()
         WHERE id = v_eff_deal_id;
    END IF;

    RETURN QUERY SELECT 'booked'::TEXT, v_booking_id;
END;
$$;
"""

CANCEL_VIEWING_FN = """
CREATE OR REPLACE FUNCTION tcs_crm_cancel_viewing(
    p_booking_id UUID,
    p_reason TEXT DEFAULT NULL
)
RETURNS TABLE(result TEXT, booking_id UUID)
LANGUAGE plpgsql
AS $$
DECLARE
    v_booking RECORD;
    v_slot RECORD;
    v_lead RECORD;
    v_prev_stage TEXT;
    v_target_stage TEXT;
    v_next_trial TIMESTAMPTZ;
BEGIN
    SELECT *
      INTO v_booking
      FROM tcs_crm_viewing_bookings
     WHERE id = p_booking_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'booking_not_found'::TEXT, NULL::UUID;
        RETURN;
    END IF;

    IF v_booking.status = 'cancelled' THEN
        RETURN QUERY SELECT 'already_cancelled'::TEXT, v_booking.id;
        RETURN;
    END IF;

    IF v_booking.status NOT IN ('pending', 'confirmed') THEN
        RETURN QUERY SELECT 'not_active'::TEXT, v_booking.id;
        RETURN;
    END IF;

    SELECT id, starts_at, status
      INTO v_slot
      FROM tcs_crm_viewing_slots
     WHERE id = v_booking.slot_id
       FOR UPDATE;

    UPDATE tcs_crm_viewing_bookings
       SET status = 'cancelled',
           cancelled_at = now(),
           updated_at = now(),
           notes = CASE
               WHEN NULLIF(BTRIM(p_reason), '') IS NOT NULL THEN
                   CASE
                       WHEN NULLIF(BTRIM(notes), '') IS NOT NULL
                       THEN notes || E'\\nCancel reason: ' || BTRIM(p_reason)
                       ELSE 'Cancel reason: ' || BTRIM(p_reason)
                   END
               ELSE notes
           END
     WHERE id = p_booking_id;

    UPDATE tcs_crm_viewing_slots
       SET status = 'open'
     WHERE id = v_booking.slot_id
       AND status = 'booked';

    IF v_booking.whatsapp_id IS NOT NULL THEN
        SELECT s.starts_at
          INTO v_next_trial
          FROM tcs_crm_viewing_bookings b
          JOIN tcs_crm_viewing_slots s ON s.id = b.slot_id
         WHERE b.whatsapp_id = v_booking.whatsapp_id
           AND b.status IN ('pending', 'confirmed')
           AND b.id <> p_booking_id
         ORDER BY s.starts_at ASC
         LIMIT 1;
    END IF;

    IF v_booking.whatsapp_id IS NOT NULL AND to_regclass('public.tcs_leads') IS NOT NULL THEN
        SELECT current_stage, previous_stage, status
          INTO v_lead
          FROM tcs_leads
         WHERE whatsapp_id = v_booking.whatsapp_id
           FOR UPDATE;

        IF FOUND THEN
            v_prev_stage := v_lead.current_stage;

            IF v_next_trial IS NOT NULL THEN
                v_target_stage := v_lead.current_stage;
                UPDATE tcs_leads
                   SET trial_datetime = v_next_trial,
                       reminder_sent = false,
                       last_message_at = now(),
                       updated_at = now()
                 WHERE whatsapp_id = v_booking.whatsapp_id;
            ELSE
                v_target_stage := NULL;
                IF v_lead.previous_stage IS NOT NULL
                   AND v_lead.previous_stage <> 'VIEWING_SCHEDULED' THEN
                    SELECT s.bot_stage_key
                      INTO v_target_stage
                      FROM tcs_crm_stages s
                      JOIN tcs_crm_pipelines p ON p.id = s.pipeline_id
                     WHERE s.kind = 'open'
                       AND s.bot_stage_key = v_lead.previous_stage
                     ORDER BY p.is_default DESC, p.sort ASC, s.sort ASC
                     LIMIT 1;
                END IF;

                IF v_target_stage IS NULL THEN
                    SELECT s.bot_stage_key
                      INTO v_target_stage
                      FROM tcs_crm_stages s
                      JOIN tcs_crm_pipelines p ON p.id = s.pipeline_id
                     WHERE s.kind = 'open'
                       AND s.bot_stage_key IS NOT NULL
                       AND s.bot_stage_key <> 'VIEWING_SCHEDULED'
                       AND s.sort < COALESCE(
                           (
                               SELECT s2.sort
                                 FROM tcs_crm_stages s2
                                WHERE s2.pipeline_id = s.pipeline_id
                                  AND s2.bot_stage_key = 'VIEWING_SCHEDULED'
                                LIMIT 1
                           ),
                           999999
                       )
                     ORDER BY p.is_default DESC, p.sort ASC, s.sort DESC
                     LIMIT 1;
                END IF;

                IF v_target_stage IS NULL THEN
                    SELECT s.bot_stage_key
                      INTO v_target_stage
                      FROM tcs_crm_stages s
                      JOIN tcs_crm_pipelines p ON p.id = s.pipeline_id
                     WHERE s.kind = 'open'
                       AND s.bot_stage_key IS NOT NULL
                       AND s.bot_stage_key <> 'VIEWING_SCHEDULED'
                     ORDER BY p.is_default DESC, p.sort ASC, s.sort ASC
                     LIMIT 1;
                END IF;

                IF v_target_stage IS NULL THEN
                    v_target_stage := 'QUALIFIED';
                END IF;

                UPDATE tcs_leads
                   SET trial_datetime = NULL,
                       reminder_sent = false,
                       previous_stage = CASE
                           WHEN current_stage IS DISTINCT FROM v_target_stage
                           THEN current_stage
                           ELSE previous_stage
                       END,
                       current_stage = v_target_stage,
                       status = CASE
                           WHEN status = 'VIEWING_BOOKED' THEN 'ACTIVE'
                           ELSE status
                       END,
                       last_message_at = now(),
                       updated_at = now()
                 WHERE whatsapp_id = v_booking.whatsapp_id;
            END IF;

            IF to_regclass('public.tcs_events') IS NOT NULL THEN
                INSERT INTO tcs_events (
                    whatsapp_id,
                    event_type,
                    from_stage,
                    to_stage,
                    payload,
                    created_at
                )
                VALUES (
                    v_booking.whatsapp_id,
                    'trial_cancelled',
                    v_prev_stage,
                    v_target_stage,
                    jsonb_build_object(
                        'booking_id', p_booking_id,
                        'slot_id', v_booking.slot_id,
                        'trial_datetime', v_slot.starts_at,
                        'reason', NULLIF(BTRIM(p_reason), '')
                    ),
                    now()
                );
            END IF;
        END IF;
    END IF;

    IF v_booking.deal_id IS NOT NULL THEN
        UPDATE tcs_crm_deals
           SET trial_at = CASE
                   WHEN trial_at = v_slot.starts_at THEN v_next_trial
                   ELSE trial_at
               END,
               last_bot_trial_at = CASE
                   WHEN last_bot_trial_at = v_slot.starts_at THEN v_next_trial
                   ELSE last_bot_trial_at
               END,
               updated_at = now()
         WHERE id = v_booking.deal_id
           AND (trial_at = v_slot.starts_at OR last_bot_trial_at = v_slot.starts_at);
    ELSIF v_booking.whatsapp_id IS NOT NULL THEN
        UPDATE tcs_crm_deals d
           SET trial_at = CASE
                   WHEN d.trial_at = v_slot.starts_at THEN v_next_trial
                   ELSE d.trial_at
               END,
               last_bot_trial_at = CASE
                   WHEN d.last_bot_trial_at = v_slot.starts_at THEN v_next_trial
                   ELSE d.last_bot_trial_at
               END,
               updated_at = now()
          FROM tcs_crm_contacts c
         WHERE d.contact_id = c.id
           AND c.whatsapp_id = v_booking.whatsapp_id
           AND d.deleted_at IS NULL
           AND (d.trial_at = v_slot.starts_at OR d.last_bot_trial_at = v_slot.starts_at);
    END IF;

    RETURN QUERY SELECT 'cancelled'::TEXT, p_booking_id;
END;
$$;
"""

RESCHEDULE_VIEWING_FN = """
CREATE OR REPLACE FUNCTION tcs_crm_reschedule_viewing(
    p_booking_id UUID,
    p_new_slot_id UUID
)
RETURNS TABLE(result TEXT, booking_id UUID)
LANGUAGE plpgsql
AS $$
DECLARE
    v_booking RECORD;
    v_old_slot RECORD;
    v_new_slot RECORD;
    v_unit RECORD;
    v_lead RECORD;
    v_eff_unit_id UUID;
    v_unit_label TEXT;
    v_building TEXT;
    v_unit_number TEXT;
    v_prev_stage TEXT;
BEGIN
    SELECT *
      INTO v_booking
      FROM tcs_crm_viewing_bookings
     WHERE id = p_booking_id
       FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'booking_not_found'::TEXT, NULL::UUID;
        RETURN;
    END IF;

    IF v_booking.status NOT IN ('pending', 'confirmed') THEN
        RETURN QUERY SELECT 'not_active'::TEXT, v_booking.id;
        RETURN;
    END IF;

    PERFORM 1
       FROM tcs_crm_viewing_slots
      WHERE id IN (v_booking.slot_id, p_new_slot_id)
      ORDER BY id
        FOR UPDATE;

    SELECT id, starts_at, status, unit_id
      INTO v_old_slot
      FROM tcs_crm_viewing_slots
     WHERE id = v_booking.slot_id;

    SELECT id, starts_at, status, unit_id
      INTO v_new_slot
      FROM tcs_crm_viewing_slots
     WHERE id = p_new_slot_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT 'slot_not_found'::TEXT, v_booking.id;
        RETURN;
    END IF;

    IF v_new_slot.starts_at <= now() THEN
        RETURN QUERY SELECT 'slot_in_past'::TEXT, v_booking.id;
        RETURN;
    END IF;

    IF p_new_slot_id = v_booking.slot_id THEN
        RETURN QUERY SELECT 'rescheduled'::TEXT, v_booking.id;
        RETURN;
    END IF;

    IF v_new_slot.status <> 'open' THEN
        RETURN QUERY SELECT 'slot_taken'::TEXT, v_booking.id;
        RETURN;
    END IF;

    IF v_new_slot.unit_id IS NOT NULL
       AND v_booking.unit_id IS NOT NULL
       AND v_new_slot.unit_id <> v_booking.unit_id THEN
        RETURN QUERY SELECT 'unit_mismatch'::TEXT, v_booking.id;
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
          FROM tcs_crm_viewing_bookings
         WHERE slot_id = p_new_slot_id
           AND status IN ('pending', 'confirmed')
           AND id <> p_booking_id
    ) THEN
        RETURN QUERY SELECT 'slot_taken'::TEXT, v_booking.id;
        RETURN;
    END IF;

    v_eff_unit_id := COALESCE(v_new_slot.unit_id, v_booking.unit_id);

    IF v_eff_unit_id IS NOT NULL THEN
        SELECT building, unit_number
          INTO v_unit
          FROM tcs_crm_units
         WHERE id = v_eff_unit_id
           AND deleted_at IS NULL;
        IF FOUND THEN
            v_building := v_unit.building;
            v_unit_number := v_unit.unit_number;
            v_unit_label := v_unit.building || ' ' || v_unit.unit_number;
        END IF;
    END IF;

    BEGIN
        UPDATE tcs_crm_viewing_bookings
           SET slot_id = p_new_slot_id,
               unit_id = v_eff_unit_id,
               updated_at = now()
         WHERE id = p_booking_id;
    EXCEPTION
        WHEN unique_violation THEN
            RETURN QUERY SELECT 'slot_taken'::TEXT, v_booking.id;
            RETURN;
    END;

    UPDATE tcs_crm_viewing_slots
       SET status = 'open'
     WHERE id = v_booking.slot_id
       AND status = 'booked';

    UPDATE tcs_crm_viewing_slots
       SET status = 'booked'
     WHERE id = p_new_slot_id;

    IF v_booking.whatsapp_id IS NOT NULL AND to_regclass('public.tcs_leads') IS NOT NULL THEN
        SELECT current_stage, previous_stage, status
          INTO v_lead
          FROM tcs_leads
         WHERE whatsapp_id = v_booking.whatsapp_id
           FOR UPDATE;

        IF FOUND THEN
            v_prev_stage := v_lead.current_stage;
            UPDATE tcs_leads
               SET trial_datetime = v_new_slot.starts_at,
                   previous_stage = CASE
                       WHEN current_stage IS DISTINCT FROM 'VIEWING_SCHEDULED'
                       THEN current_stage
                       ELSE previous_stage
                   END,
                   current_stage = 'VIEWING_SCHEDULED',
                   status = 'VIEWING_BOOKED',
                   reminder_sent = false,
                   lead_data = CASE
                       WHEN v_unit_label IS NOT NULL
                       THEN COALESCE(lead_data, '{}'::jsonb)
                            || jsonb_build_object('unit', v_unit_label)
                       ELSE lead_data
                   END,
                   last_message_at = now(),
                   updated_at = now()
             WHERE whatsapp_id = v_booking.whatsapp_id;

            IF to_regclass('public.tcs_events') IS NOT NULL THEN
                INSERT INTO tcs_events (
                    whatsapp_id,
                    event_type,
                    from_stage,
                    to_stage,
                    payload,
                    created_at
                )
                VALUES (
                    v_booking.whatsapp_id,
                    'trial_rescheduled',
                    v_prev_stage,
                    'VIEWING_SCHEDULED',
                    jsonb_build_object(
                        'booking_id', p_booking_id,
                        'old_slot_id', v_booking.slot_id,
                        'new_slot_id', p_new_slot_id,
                        'old_trial_datetime', v_old_slot.starts_at,
                        'trial_datetime', v_new_slot.starts_at,
                        'unit_id', v_eff_unit_id,
                        'building', v_building,
                        'unit_number', v_unit_number
                    ),
                    now()
                );
            END IF;
        END IF;
    END IF;

    IF v_booking.deal_id IS NOT NULL THEN
        UPDATE tcs_crm_deals
           SET trial_at = v_new_slot.starts_at,
               last_bot_trial_at = v_new_slot.starts_at,
               updated_at = now()
         WHERE id = v_booking.deal_id;
    ELSIF v_booking.whatsapp_id IS NOT NULL THEN
        UPDATE tcs_crm_deals d
           SET trial_at = v_new_slot.starts_at,
               last_bot_trial_at = v_new_slot.starts_at,
               updated_at = now()
          FROM tcs_crm_contacts c
         WHERE d.contact_id = c.id
           AND c.whatsapp_id = v_booking.whatsapp_id
           AND d.deleted_at IS NULL;
    END IF;

    RETURN QUERY SELECT 'rescheduled'::TEXT, p_booking_id;
END;
$$;
"""


def upgrade() -> None:
    op.create_table(
        "tcs_crm_units",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("building", sa.String(255), nullable=False),
        sa.Column("unit_number", sa.String(64), nullable=False),
        sa.Column("beds", sa.Integer(), nullable=False),
        sa.Column("baths", sa.Numeric(4, 1), nullable=False),
        sa.Column("rent_usd", sa.Integer(), nullable=False),
        sa.Column("deposit_usd", sa.Integer(), nullable=True),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column("pets_policy", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="available"),
        sa.Column(
            "photos",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("deleted_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('available', 'leased', 'hidden')",
            name="ck_tcs_crm_units_status",
        ),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_tcs_crm_units_building_number"
            " ON tcs_crm_units (building, unit_number)"
            " WHERE deleted_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_tcs_crm_units_status"
            " ON tcs_crm_units (status)"
            " WHERE deleted_at IS NULL"
        )
    )

    op.create_table(
        "tcs_crm_viewing_slots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False, server_default="60"),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tcs_crm_units.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tcs_crm_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("created_at"),
        sa.CheckConstraint(
            "status IN ('open', 'booked', 'blocked')",
            name="ck_tcs_crm_viewing_slots_status",
        ),
        sa.CheckConstraint(
            "duration_min > 0",
            name="ck_tcs_crm_viewing_slots_duration",
        ),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_tcs_crm_viewing_slots_starts_unit"
            " ON tcs_crm_viewing_slots"
            f" (starts_at, COALESCE(unit_id, '{ZERO_UUID}'::uuid))"
        )
    )
    op.create_index(
        "ix_tcs_crm_viewing_slots_starts_status",
        "tcs_crm_viewing_slots",
        ["starts_at", "status"],
    )
    op.create_index(
        "ix_tcs_crm_viewing_slots_unit_id",
        "tcs_crm_viewing_slots",
        ["unit_id"],
    )

    op.create_table(
        "tcs_crm_viewing_bookings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tcs_crm_viewing_slots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tcs_crm_units.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "deal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tcs_crm_deals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tcs_crm_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("whatsapp_id", sa.Text(), nullable=True),
        sa.Column("client_name", sa.String(255), nullable=True),
        sa.Column("client_phone", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="confirmed"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tcs_crm_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("cancelled_at", nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'no_show')",
            name="ck_tcs_crm_viewing_bookings_status",
        ),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_tcs_crm_viewing_bookings_active_slot"
            " ON tcs_crm_viewing_bookings (slot_id)"
            " WHERE status IN ('pending', 'confirmed')"
        )
    )
    op.create_index(
        "ix_tcs_crm_viewing_bookings_unit_id",
        "tcs_crm_viewing_bookings",
        ["unit_id"],
    )
    op.create_index(
        "ix_tcs_crm_viewing_bookings_deal_id",
        "tcs_crm_viewing_bookings",
        ["deal_id"],
    )
    op.create_index(
        "ix_tcs_crm_viewing_bookings_contact_id",
        "tcs_crm_viewing_bookings",
        ["contact_id"],
    )
    op.create_index(
        "ix_tcs_crm_viewing_bookings_whatsapp_id",
        "tcs_crm_viewing_bookings",
        ["whatsapp_id"],
    )

    op.drop_constraint("ck_tcs_crm_imports_entity", "tcs_crm_imports", type_="check")
    op.create_check_constraint(
        "ck_tcs_crm_imports_entity",
        "tcs_crm_imports",
        "entity IN ('contact', 'deal', 'unit')",
    )

    op.execute(sa.text(BOOK_VIEWING_FN))
    op.execute(sa.text(CANCEL_VIEWING_FN))
    op.execute(sa.text(RESCHEDULE_VIEWING_FN))


def downgrade() -> None:
    op.execute(sa.text("DROP FUNCTION IF EXISTS tcs_crm_reschedule_viewing(UUID, UUID)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS tcs_crm_cancel_viewing(UUID, TEXT)"))
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS tcs_crm_book_viewing("
            "TEXT, UUID, UUID, TEXT, TEXT, UUID, UUID, TEXT, UUID)"
        )
    )

    op.drop_constraint("ck_tcs_crm_imports_entity", "tcs_crm_imports", type_="check")
    op.create_check_constraint(
        "ck_tcs_crm_imports_entity",
        "tcs_crm_imports",
        "entity IN ('contact', 'deal')",
    )

    op.drop_table("tcs_crm_viewing_bookings")
    op.drop_table("tcs_crm_viewing_slots")
    op.drop_table("tcs_crm_units")
