import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from order_api.core.exceptions import conflict, not_found
from order_api.models import Customer, Product, User
from order_api.repositories.base import TenantRepository
from order_api.repositories.order_repository import lock_products
from order_api.repositories.resources import (
    customer_repository,
    product_repository,
    user_repository,
)
from order_api.schemas import (
    CustomerCreate,
    CustomerPatch,
    ProductCreate,
    ProductPatch,
    StockAdjustment,
    UserCreate,
    UserPatch,
)
from order_api.schemas.pagination import ListQuery
from order_api.services.orders import audit


def list_resources(db: Session, repository: TenantRepository, actor: User, query: ListQuery):
    return repository.list(db, actor.organization_id, query)


def get_resource(
    db: Session, repository: TenantRepository, object_id: uuid.UUID, actor: User, label: str
):
    obj = repository.get(db, object_id, actor.organization_id)
    if obj is None:
        raise not_found(label)
    return obj


def create_customer(db: Session, payload: CustomerCreate, actor: User) -> Customer:
    obj = Customer(organization_id=actor.organization_id, **payload.model_dump(mode="json"))
    customer_repository.add(db, obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_customer(
    db: Session, customer_id: uuid.UUID, payload: CustomerPatch, actor: User
) -> Customer:
    obj = get_resource(db, customer_repository, customer_id, actor, "Customer")
    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete_customer(db: Session, customer_id: uuid.UUID, actor: User) -> None:
    obj = get_resource(db, customer_repository, customer_id, actor, "Customer")
    customer_repository.delete(db, obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("Customer is referenced by an order.") from None


def create_product(db: Session, payload: ProductCreate, actor: User) -> Product:
    obj = Product(organization_id=actor.organization_id, **payload.model_dump())
    product_repository.add(db, obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("SKU already exists in this organization.") from None
    db.refresh(obj)
    return obj


def update_product(
    db: Session, product_id: uuid.UUID, payload: ProductPatch, actor: User
) -> Product:
    obj = get_resource(db, product_repository, product_id, actor, "Product")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    db.commit()
    db.refresh(obj)
    return obj


def deactivate_product(db: Session, product_id: uuid.UUID, actor: User) -> None:
    obj = get_resource(db, product_repository, product_id, actor, "Product")
    obj.is_active = False
    db.commit()


def adjust_stock(
    db: Session, product_id: uuid.UUID, payload: StockAdjustment, actor: User
) -> Product:
    obj = lock_products(db, [product_id], actor.organization_id).get(product_id)
    if obj is None:
        raise not_found("Product")
    if obj.stock_quantity + payload.quantity_delta < 0:
        raise conflict(
            "Stock cannot become negative.",
            {"available": obj.stock_quantity, "adjustment": payload.quantity_delta},
        )
    before = obj.stock_quantity
    obj.stock_quantity += payload.quantity_delta
    audit(
        db,
        actor,
        "product",
        obj.id,
        "stock_adjusted",
        {"from": before, "to": obj.stock_quantity, "reason": payload.reason},
    )
    db.commit()
    db.refresh(obj)
    return obj


def create_user(db: Session, payload: UserCreate, actor: User, password_hash: str) -> User:
    obj = User(
        organization_id=actor.organization_id,
        email=payload.email.lower(),
        password_hash=password_hash,
        role=payload.role,
        is_active=payload.is_active,
    )
    user_repository.add(db, obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("Email already exists in this organization.") from None
    db.refresh(obj)
    return obj


def update_user(
    db: Session, user_id: uuid.UUID, payload: UserPatch, actor: User, password_hash: str | None
) -> User:
    obj = get_resource(db, user_repository, user_id, actor, "User")
    values = payload.model_dump(exclude_unset=True)
    values.pop("password", None)
    if "email" in values:
        values["email"] = str(values["email"]).lower()
    if password_hash:
        values["password_hash"] = password_hash
    for field, value in values.items():
        setattr(obj, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict("Email already exists in this organization.") from None
    db.refresh(obj)
    return obj


def deactivate_user(db: Session, user_id: uuid.UUID, actor: User) -> None:
    obj = get_resource(db, user_repository, user_id, actor, "User")
    if obj.id == actor.id:
        raise conflict("You cannot deactivate yourself.")
    obj.is_active = False
    db.commit()
