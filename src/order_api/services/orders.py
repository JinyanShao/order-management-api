import hashlib
import json
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from order_api.core.exceptions import AppError, not_found
from order_api.models import (
    AuditLog,
    IdempotencyRecord,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    User,
)
from order_api.repositories.order_repository import (
    find_active_product,
    find_customer,
    find_idempotency_record,
    find_order,
    lock_products,
)
from order_api.schemas import OrderCreate, OrderItemCreate, OrderItemPatch, OrderPatch


def audit(
    db: Session,
    user: User,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    changes: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            organization_id=user.organization_id,
            actor_id=user.id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            changes=changes,
        )
    )


def get_order(db: Session, order_id: uuid.UUID, user: User, *, lock: bool = False) -> Order:
    order = find_order(db, order_id, user.organization_id, lock=lock)
    if order is None:
        raise not_found("Order")
    return order


def check_version(order: Order, version: int) -> None:
    if order.version != version:
        raise AppError(
            "OPTIMISTIC_LOCK_CONFLICT",
            "The order was modified; reload it and retry.",
            status_code=409,
            details={"current_version": order.version, "provided_version": version},
        )


def ensure_draft(order: Order) -> None:
    if order.status != OrderStatus.draft:
        raise AppError(
            "INVALID_ORDER_TRANSITION",
            "Only draft orders can be modified.",
            status_code=409,
        )


def recalculate(order: Order) -> None:
    order.total_amount_cents = sum(item.line_total_cents for item in order.items)
    order.version += 1


def product_for_item(db: Session, item: OrderItemCreate, user: User) -> Product:
    product = find_active_product(db, item.product_id, user.organization_id)
    if product is None:
        raise not_found("Active product")
    return product


def create_order(db: Session, payload: OrderCreate, user: User, key: str) -> Order:
    request_hash = hashlib.sha256(
        json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    existing = find_idempotency_record(db, user.organization_id, user.id, key)
    if existing:
        if existing.request_hash != request_hash:
            raise AppError(
                "IDEMPOTENCY_CONFLICT",
                "Idempotency-Key was already used with another request.",
                status_code=409,
            )
        return get_order(db, existing.order_id, user)

    customer = find_customer(db, payload.customer_id, user.organization_id)
    if customer is None:
        raise not_found("Customer")
    if len({item.product_id for item in payload.items}) != len(payload.items):
        raise AppError("VALIDATION_ERROR", "Duplicate products are not allowed.", status_code=422)
    try:
        order = Order(
            organization_id=user.organization_id,
            customer_id=payload.customer_id,
            currency=payload.currency,
            created_by=user.id,
        )
        db.add(order)
        db.flush()
        for requested in payload.items:
            product = product_for_item(db, requested, user)
            order.items.append(
                OrderItem(
                    organization_id=user.organization_id,
                    product_id=product.id,
                    quantity=requested.quantity,
                    unit_price_cents=product.unit_price_cents,
                    line_total_cents=product.unit_price_cents * requested.quantity,
                )
            )
        order.total_amount_cents = sum(item.line_total_cents for item in order.items)
        audit(db, user, "order", order.id, "created", {"status": "draft"})
        db.add(
            IdempotencyRecord(
                organization_id=user.organization_id,
                user_id=user.id,
                key=key,
                request_hash=request_hash,
                order_id=order.id,
            )
        )
        db.commit()
        db.refresh(order)
        return order
    except IntegrityError:
        db.rollback()
        record = find_idempotency_record(db, user.organization_id, user.id, key)
        if record and record.request_hash == request_hash:
            return get_order(db, record.order_id, user)
        raise AppError("IDEMPOTENCY_CONFLICT", "Idempotency conflict.", status_code=409) from None


def transition_order(
    db: Session, order_id: uuid.UUID, user: User, version: int, target: OrderStatus
) -> Order:
    order = get_order(db, order_id, user, lock=True)
    check_version(order, version)
    allowed = {
        OrderStatus.confirmed: {OrderStatus.draft},
        OrderStatus.processing: {OrderStatus.confirmed},
        OrderStatus.shipped: {OrderStatus.processing},
        OrderStatus.cancelled: {
            OrderStatus.draft,
            OrderStatus.confirmed,
            OrderStatus.processing,
        },
    }
    if order.status not in allowed[target]:
        raise AppError(
            "INVALID_ORDER_TRANSITION",
            f"Cannot transition from {order.status.value} to {target.value}.",
            status_code=409,
            details={"from": order.status.value, "to": target.value},
        )
    previous = order.status
    if target == OrderStatus.confirmed:
        if not order.items:
            raise AppError(
                "INVALID_ORDER_TRANSITION", "Cannot confirm an empty order.", status_code=409
            )
        product_ids = [item.product_id for item in order.items]
        products = lock_products(db, product_ids, user.organization_id)
        for item in order.items:
            product = products.get(item.product_id)
            if product is None or product.stock_quantity < item.quantity:
                available = product.stock_quantity if product else 0
                sku = product.sku if product else str(item.product_id)
                raise AppError(
                    "INSUFFICIENT_STOCK",
                    f"Insufficient stock for product {sku}.",
                    status_code=409,
                    details={"available": available, "requested": item.quantity},
                )
        for item in order.items:
            products[item.product_id].stock_quantity -= item.quantity
    elif target == OrderStatus.cancelled and previous in {
        OrderStatus.confirmed,
        OrderStatus.processing,
    }:
        products = lock_products(
            db, [item.product_id for item in order.items], user.organization_id
        )
        for item in order.items:
            products[item.product_id].stock_quantity += item.quantity
    order.status = target
    order.version += 1
    audit(
        db,
        user,
        "order",
        order.id,
        "status_changed",
        {"from": previous.value, "to": target.value},
    )
    db.commit()
    db.refresh(order)
    return order


def update_order(db: Session, order_id: uuid.UUID, payload: OrderPatch, user: User) -> Order:
    order = get_order(db, order_id, user, lock=True)
    ensure_draft(order)
    check_version(order, payload.version)
    values = payload.model_dump(exclude_unset=True, exclude={"version"})
    if (customer_id := values.get("customer_id")) and find_customer(
        db, customer_id, user.organization_id
    ) is None:
        raise not_found("Customer")
    for field, value in values.items():
        setattr(order, field, value.upper() if field == "currency" else value)
    order.version += 1
    audit(db, user, "order", order.id, "updated", values)
    db.commit()
    db.refresh(order)
    return order


def delete_draft(db: Session, order_id: uuid.UUID, version: int, user: User) -> None:
    order = get_order(db, order_id, user, lock=True)
    ensure_draft(order)
    check_version(order, version)
    audit(db, user, "order", order.id, "deleted", {})
    db.delete(order)
    db.commit()


def add_item(
    db: Session, order_id: uuid.UUID, payload: OrderItemCreate, version: int, user: User
) -> Order:
    order = get_order(db, order_id, user, lock=True)
    ensure_draft(order)
    check_version(order, version)
    product = product_for_item(db, payload, user)
    if any(item.product_id == product.id for item in order.items):
        raise AppError("RESOURCE_CONFLICT", "Product already exists in order.", status_code=409)
    order.items.append(
        OrderItem(
            organization_id=user.organization_id,
            product_id=product.id,
            quantity=payload.quantity,
            unit_price_cents=product.unit_price_cents,
            line_total_cents=product.unit_price_cents * payload.quantity,
        )
    )
    recalculate(order)
    audit(db, user, "order", order.id, "item_added", {"product_id": str(product.id)})
    db.commit()
    db.refresh(order)
    return order


def update_item(
    db: Session,
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: OrderItemPatch,
    user: User,
) -> Order:
    order = get_order(db, order_id, user, lock=True)
    ensure_draft(order)
    check_version(order, payload.version)
    item = next((item for item in order.items if item.id == item_id), None)
    if item is None:
        raise not_found("Order item")
    item.quantity = payload.quantity
    item.line_total_cents = item.unit_price_cents * item.quantity
    recalculate(order)
    audit(db, user, "order", order.id, "item_updated", {"item_id": str(item.id)})
    db.commit()
    db.refresh(order)
    return order


def delete_item(
    db: Session, order_id: uuid.UUID, item_id: uuid.UUID, version: int, user: User
) -> Order:
    order = get_order(db, order_id, user, lock=True)
    ensure_draft(order)
    check_version(order, version)
    item = next((item for item in order.items if item.id == item_id), None)
    if item is None:
        raise not_found("Order item")
    order.items.remove(item)
    recalculate(order)
    audit(db, user, "order", order.id, "item_deleted", {"item_id": str(item_id)})
    db.commit()
    db.refresh(order)
    return order
