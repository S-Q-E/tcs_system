from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

UnitStatus = Literal["available", "leased", "hidden"]
SlotStatus = Literal["open", "booked", "blocked"]
SlotWritableStatus = Literal["open", "blocked"]
BookingStatus = Literal["pending", "confirmed", "cancelled", "no_show"]
BookingPatchStatus = Literal["pending", "confirmed", "no_show"]


class UnitOut(BaseModel):
    id: uuid.UUID
    building: str
    unit_number: str
    beds: int
    baths: float
    rent_usd: int
    deposit_usd: int | None
    available_from: date | None
    pets_policy: str | None
    allows_dogs: bool
    allows_cats: bool
    description: str | None
    status: str
    photos: list[str]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None

    model_config = {"from_attributes": True}


class UnitCreate(BaseModel):
    building: str = Field(min_length=1, max_length=255)
    unit_number: str = Field(min_length=1, max_length=64)
    beds: int = Field(ge=0, le=20)
    baths: float = Field(gt=0, le=20)
    rent_usd: int = Field(ge=0)
    deposit_usd: int | None = Field(default=None, ge=0)
    available_from: date | None = None
    pets_policy: str | None = Field(default=None, max_length=500)
    allows_dogs: bool | None = None
    allows_cats: bool | None = None
    description: str | None = Field(default=None, max_length=4000)
    status: UnitStatus = "available"
    photos: list[str] = Field(default_factory=list, max_length=30)


class UnitUpdate(BaseModel):
    building: str | None = Field(default=None, min_length=1, max_length=255)
    unit_number: str | None = Field(default=None, min_length=1, max_length=64)
    beds: int | None = Field(default=None, ge=0, le=20)
    baths: float | None = Field(default=None, gt=0, le=20)
    rent_usd: int | None = Field(default=None, ge=0)
    deposit_usd: int | None = Field(default=None, ge=0)
    available_from: date | None = None
    pets_policy: str | None = Field(default=None, max_length=500)
    allows_dogs: bool | None = None
    allows_cats: bool | None = None
    description: str | None = Field(default=None, max_length=4000)
    status: UnitStatus | None = None
    photos: list[str] | None = Field(default=None, max_length=30)


class UnitListOut(BaseModel):
    items: list[UnitOut]
    total: int


class SlotBookingBriefOut(BaseModel):
    id: uuid.UUID
    status: str
    unit_id: uuid.UUID | None = None
    unit_label: str | None = None
    deal_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    whatsapp_id: str | None = None
    client_name: str | None = None
    client_phone: str | None = None
    notes: str | None = None


class ViewingSlotOut(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    duration_min: int
    unit_id: uuid.UUID | None
    unit_label: str | None = None
    status: str
    created_by: uuid.UUID | None
    created_at: datetime
    booking: SlotBookingBriefOut | None = None

    model_config = {"from_attributes": True}


class ViewingSlotCreate(BaseModel):
    starts_at: datetime
    duration_min: int = Field(default=60, ge=15, le=480)
    unit_id: uuid.UUID | None = None
    status: SlotWritableStatus = "open"


class ViewingSlotUpdate(BaseModel):
    starts_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=15, le=480)
    unit_id: uuid.UUID | None = None
    status: SlotWritableStatus | None = None


class ViewingSlotGenerateIn(BaseModel):
    days: int = Field(default=14, ge=1, le=90)
    unit_id: uuid.UUID | None = None
    duration_min: int = Field(default=60, ge=15, le=180)


class ViewingSlotGenerateOut(BaseModel):
    created: int
    total_candidates: int


class ViewingSlotListOut(BaseModel):
    items: list[ViewingSlotOut]
    total: int


class ViewingBookingOut(BaseModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    slot_starts_at: datetime | None = None
    slot_duration_min: int | None = None
    unit_id: uuid.UUID | None
    unit_label: str | None = None
    deal_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    whatsapp_id: str | None
    client_name: str | None
    client_phone: str | None
    status: str
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    cancelled_at: datetime | None

    model_config = {"from_attributes": True}


class ViewingBookingCreate(BaseModel):
    slot_id: uuid.UUID
    unit_id: uuid.UUID | None = None
    deal_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    whatsapp_id: str | None = Field(default=None, max_length=128)
    client_name: str | None = Field(default=None, max_length=255)
    client_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)


class ViewingBookingUpdate(BaseModel):
    status: BookingPatchStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)
    client_name: str | None = Field(default=None, max_length=255)
    client_phone: str | None = Field(default=None, max_length=64)


class ViewingBookingCancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ViewingBookingRescheduleIn(BaseModel):
    new_slot_id: uuid.UUID


class ViewingBookingListOut(BaseModel):
    items: list[ViewingBookingOut]
    total: int
