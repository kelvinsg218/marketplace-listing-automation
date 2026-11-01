from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from mla_api.db import as_aware

from mla_api.domain.catalog import normalize_gtin, sku_problem
from mla_api.models import ProductStatus, Role


# Always serialized with an offset (SQLite hands back naive UTC values; browsers would read them as local time).
UtcDatetime = Annotated[datetime, AfterValidator(as_aware)]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -------------------------------------------------------------------------------------------------------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(max_length=128)
    organization_name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class ResetRequestIn(BaseModel):
    email: EmailStr


class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=128)


class UserOut(_Out):
    id: uuid.UUID
    name: str
    email: str


class OrgOut(_Out):
    id: uuid.UUID
    name: str
    slug: str


class MembershipOut(BaseModel):
    organization: OrgOut
    role: str


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]


# --- organizations ----------------------------------------------------------------------------------------------
class OrgCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MemberOut(BaseModel):
    user: UserOut
    role: str
    created_at: UtcDatetime


class MemberAddIn(BaseModel):
    email: EmailStr
    role: Role


class MemberRoleIn(BaseModel):
    role: Role


# --- products ---------------------------------------------------------------------------------------------------
def _clean_gtin(v: str) -> str:
    digits = normalize_gtin(v)
    if v.strip() and len(digits) not in (8, 12, 13, 14):
        raise ValueError("GTIN/EAN precisa ter 8, 12, 13 ou 14 dígitos.")
    return digits


class _ProductFields(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="", max_length=120)
    model: str = Field(default="", max_length=120)
    gtin: str = Field(default="", max_length=32)
    description: str = Field(default="", max_length=50_000)
    price_cents: int | None = Field(default=None, ge=0, le=10**11)
    cost_cents: int | None = Field(default=None, ge=0, le=10**11)
    stock: int = Field(default=0, ge=0, le=10**9)
    status: ProductStatus = ProductStatus.DRAFT
    attributes: dict[str, str] = Field(default_factory=dict, max_length=200)

    _gtin = field_validator("gtin")(lambda cls, v: _clean_gtin(v))


class ProductIn(_ProductFields):
    sku: str = Field(min_length=1, max_length=64)

    @field_validator("sku")
    @classmethod
    def _sku(cls, v: str) -> str:
        problem = sku_problem(v)
        if problem:
            raise ValueError(problem)
        return v.strip()


class ProductPatch(BaseModel):
    """Partial update: only the fields sent are changed. SKU is immutable here (it identifies the product)."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    gtin: str | None = Field(default=None, max_length=32)
    description: str | None = Field(default=None, max_length=50_000)
    price_cents: int | None = Field(default=None, ge=0, le=10**11)
    cost_cents: int | None = Field(default=None, ge=0, le=10**11)
    stock: int | None = Field(default=None, ge=0, le=10**9)
    status: ProductStatus | None = None
    attributes: dict[str, str] | None = Field(default=None, max_length=200)

    _gtin = field_validator("gtin")(lambda cls, v: v if v is None else _clean_gtin(v))


class PendingOut(BaseModel):
    field: str
    message: str
    severity: str


class ProductOut(_Out):
    id: uuid.UUID
    sku: str
    name: str
    brand: str
    model: str
    gtin: str
    description: str
    price_cents: int | None
    cost_cents: int | None
    stock: int
    status: str
    attributes: dict
    created_at: UtcDatetime
    updated_at: UtcDatetime
    pendings: list[PendingOut] = []


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int


# --- dashboard / audit ------------------------------------------------------------------------------------------
class AuditOut(_Out):
    id: uuid.UUID
    action: str
    target_type: str
    target_id: str
    details: dict
    created_at: UtcDatetime
    user_name: str | None = None


class DashboardOut(BaseModel):
    products_total: int
    products_complete: int
    products_with_pendings: int
    products_by_status: dict[str, int]
    # Modules not built yet report None (the UI says "not available yet" instead of showing a fake zero).
    batches_total: int | None = None
    exports_total: int | None = None
    validation_errors: int | None = None
    recent_activity: list[AuditOut]
