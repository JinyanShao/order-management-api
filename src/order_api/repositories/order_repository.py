import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from order_api.models import Customer, IdempotencyRecord, Order, Product


def find_order(
    db: Session, order_id: uuid.UUID, organization_id: uuid.UUID, *, lock: bool = False
) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id, Order.organization_id == organization_id)
        .options(selectinload(Order.items))
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def find_customer(db: Session, customer_id: uuid.UUID, organization_id: uuid.UUID):
    return db.scalar(
        select(Customer).where(
            Customer.id == customer_id, Customer.organization_id == organization_id
        )
    )


def find_active_product(db: Session, product_id: uuid.UUID, organization_id: uuid.UUID):
    return db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.organization_id == organization_id,
            Product.is_active.is_(True),
        )
    )


def lock_products(
    db: Session, product_ids: list[uuid.UUID], organization_id: uuid.UUID
) -> dict[uuid.UUID, Product]:
    products = db.scalars(
        select(Product)
        .where(Product.id.in_(product_ids), Product.organization_id == organization_id)
        .order_by(Product.id)
        .with_for_update()
    )
    return {product.id: product for product in products}


def find_idempotency_record(
    db: Session, organization_id: uuid.UUID, user_id: uuid.UUID, key: str
) -> IdempotencyRecord | None:
    return db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.organization_id == organization_id,
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.key == key,
        )
    )
