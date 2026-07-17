import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from order_api.core.exceptions import AppError
from order_api.models import AuditLog
from order_api.repositories.base import PageResult
from order_api.schemas.pagination import ListQuery


def list_order_audits(
    db: Session, organization_id: uuid.UUID, order_id: uuid.UUID, query: ListQuery
) -> PageResult[AuditLog]:
    stmt = select(AuditLog).where(
        AuditLog.organization_id == organization_id,
        AuditLog.entity_type == "order",
        AuditLog.entity_id == order_id,
    )
    if query.search:
        pattern = f"%{query.search}%"
        stmt = stmt.where(or_(AuditLog.action.ilike(pattern), AuditLog.entity_type.ilike(pattern)))
    if query.status:
        stmt = stmt.where(AuditLog.action == query.status)
    if query.created_from:
        stmt = stmt.where(AuditLog.created_at >= query.created_from)
    if query.created_to:
        stmt = stmt.where(AuditLog.created_at <= query.created_to)
    sortable = {"created_at": AuditLog.created_at, "action": AuditLog.action}
    descending = query.sort.startswith("-")
    name = query.sort.removeprefix("-")
    column = sortable.get(name)
    if column is None:
        raise AppError(
            "VALIDATION_ERROR",
            f"Unsupported sort field '{name}'.",
            status_code=422,
            details={"allowed": sorted(sortable)},
        )
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    ordering = column.desc() if descending else column.asc()
    items = db.scalars(
        stmt.order_by(ordering, AuditLog.id.asc())
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
    ).all()
    pages = (total + query.page_size - 1) // query.page_size
    return PageResult(list(items), query.page, query.page_size, total, pages)
