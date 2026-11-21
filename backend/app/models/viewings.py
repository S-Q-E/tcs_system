from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

UNIT_STATUS_AVAILABLE = "available"
UNIT_STATUS_LEASED = "leased"
UNIT_STATUS_HIDDEN = "hidden"
VALID_UNIT_STATUSES = (UNIT_STATUS_AVAILABLE, UNIT_STATUS_LEASED, UNIT_STATUS_HIDDEN)

SLOT_STATUS_OPEN = "open"
SLOT_STATUS_BOOKED = "booked"
SLOT_STATUS_BLOCKED = "blocked"
VALID_SLOT_STATUSES = (SLOT_STATUS_OPEN, SLOT_STATUS_BOOKED, SLOT_STATUS_BLOCKED)

BOOKING_STATUS_PENDING = "pending"
BOOKING_STATUS_CONFIRMED = "confirmed"
BOOKING_STATUS_CANCELLED = "cancelled"
BOOKING_STATUS_NO_SHOW = "no_show"
ACTIVE_BOOKING_STATUSES = (BOOKING_STATUS_PENDING, BOOKING_STATUS_CONFIRMED)
VALID_BOOKING_STATUSES = (
    BOOKING_STATUS_PENDING,
    BOOKING_STATUS_CONFIRMED,
    BOOKING_STATUS_CANCELLED,
    BOOKING_STATUS_NO_SHOW,
)

ZERO_UUID = "00000000-0000-0000-0000-000000000000"


class CrmUnit(Base):
    """Leasing unit managed in CRM and searched by the bot."""

    __tablename__ = "tcs_crm_units"
    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'leased', 'hidden')",
            name="ck_tcs_crm_units_status",
        ),
        Index(
            "uq_tcs_crm_units_building_number",
            "building",
            "unit_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_tcs_crm_units_status",
            "status",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    building: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_number: Mapped[str] = mapped_column(String(64), nullable=False)
    beds: Mapped[int] = mapped_column(Integer, nullable=False)
    baths: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    rent_usd: Mapped[int] = mapped_column(Integer, nullable=False)
    deposit_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    available_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    pets_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    allows_dogs: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    allows_cats: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=UNIT_STATUS_AVAILABLE
    )
    photos: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CrmViewingSlot(Base):
    """Viewing time slot stored in UTC and displayed in America/New_York."""

    __tablename__ = "tcs_crm_viewing_slots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'booked', 'blocked')",
            name="ck_tcs_crm_viewing_slots_status",
        ),
        CheckConstraint(
            "duration_min > 0",
            name="ck_tcs_crm_viewing_slots_duration",
        ),
        Index(
            "uq_tcs_crm_viewing_slots_starts_unit",
            "starts_at",
            text(f"COALESCE(unit_id, '{ZERO_UUID}'::uuid)"),
            unique=True,
        ),
        Index("ix_tcs_crm_viewing_slots_starts_status", "starts_at", "status"),
        Index("ix_tcs_crm_viewing_slots_unit_id", "unit_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tcs_crm_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=SLOT_STATUS_OPEN)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tcs_crm_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CrmViewingBooking(Base):
    """Viewing booking (capacity = 1 active booking per slot)."""

    __tablename__ = "tcs_crm_viewing_bookings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled', 'no_show')",
            name="ck_tcs_crm_viewing_bookings_status",
        ),
        Index(
            "uq_tcs_crm_viewing_bookings_active_slot",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'confirmed')"),
        ),
        Index("ix_tcs_crm_viewing_bookings_unit_id", "unit_id"),
        Index("ix_tcs_crm_viewing_bookings_deal_id", "deal_id"),
        Index("ix_tcs_crm_viewing_bookings_contact_id", "contact_id"),
        Index("ix_tcs_crm_viewing_bookings_whatsapp_id", "whatsapp_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    slot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tcs_crm_viewing_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tcs_crm_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tcs_crm_deals.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tcs_crm_contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    whatsapp_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=BOOKING_STATUS_CONFIRMED
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tcs_crm_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
