import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from order_api.models import OrderStatus, UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=1, max_length=200)
    organization_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    organization_slug: str
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    is_active: bool = True


class UserPatch(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: UserRole | None = None
    is_active: bool | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class CustomerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)


class CustomerOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    email: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    unit_price_cents: int = Field(ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    is_active: bool = True


class ProductPatch(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit_price_cents: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class StockAdjustment(BaseModel):
    quantity_delta: int
    reason: str = Field(min_length=1, max_length=200)


class ProductOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    sku: str
    name: str
    unit_price_cents: int
    stock_quantity: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrderItemCreate(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class OrderItemPatch(BaseModel):
    quantity: int = Field(gt=0)
    version: int = Field(gt=0)


class OrderItemOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    order_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    unit_price_cents: int
    line_total_cents: int


class OrderCreate(BaseModel):
    customer_id: uuid.UUID
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    items: list[OrderItemCreate] = Field(min_length=1)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()


class OrderPatch(BaseModel):
    customer_id: uuid.UUID | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    version: int = Field(gt=0)


class VersionRequest(BaseModel):
    version: int = Field(gt=0)


class OrderOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    status: OrderStatus
    currency: str
    total_amount_cents: int
    version: int
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]


class AuditLogOut(ORMModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    actor_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    changes: dict
    created_at: datetime
