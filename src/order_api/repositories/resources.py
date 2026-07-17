import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from order_api.models import AuditLog, Customer, Order, Product, User, UserRole
from order_api.repositories.base import TenantRepository

user_repository = TenantRepository(
    User,
    sortable={"created_at": User.created_at, "email": User.email, "role": User.role},
    searchable=(User.email,),
)
customer_repository = TenantRepository(
    Customer,
    sortable={"created_at": Customer.created_at, "name": Customer.name, "email": Customer.email},
    searchable=(Customer.name, Customer.email),
)
product_repository = TenantRepository(
    Product,
    sortable={
        "created_at": Product.created_at,
        "name": Product.name,
        "sku": Product.sku,
        "stock_quantity": Product.stock_quantity,
        "unit_price_cents": Product.unit_price_cents,
    },
    searchable=(Product.name, Product.sku),
)
order_repository = TenantRepository(
    Order,
    sortable={
        "created_at": Order.created_at,
        "updated_at": Order.updated_at,
        "status": Order.status,
        "total_amount_cents": Order.total_amount_cents,
    },
    status_column=Order.status,
    eager_options=(selectinload(Order.items),),
)
audit_repository = TenantRepository(
    AuditLog,
    sortable={"created_at": AuditLog.created_at, "action": AuditLog.action},
    searchable=(AuditLog.entity_type, AuditLog.action),
    status_column=AuditLog.action,
)


def lock_active_owners(db: Session, organization_id: uuid.UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.organization_id == organization_id,
                User.role == UserRole.owner,
                User.is_active.is_(True),
            )
            .order_by(User.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
