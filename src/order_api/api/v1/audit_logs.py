import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from order_api.api.dependencies import require_roles
from order_api.core.database import get_db
from order_api.models import User, UserRole
from order_api.repositories.audit_repository import list_order_audits
from order_api.repositories.resources import audit_repository
from order_api.schemas import AuditLogOut
from order_api.schemas.pagination import ListQuery, Page
from order_api.services.orders import get_order
from order_api.services.resources import list_resources

router = APIRouter(tags=["audit"])
ALL = (UserRole.owner, UserRole.manager, UserRole.staff, UserRole.viewer)


@router.get("/audit-logs", response_model=Page[AuditLogOut])
def list_audit_logs(
    query: ListQuery = Depends(),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return list_resources(db, audit_repository, actor, query)


@router.get("/orders/{order_id}/audit-logs", response_model=Page[AuditLogOut])
def order_audit_logs(
    order_id: uuid.UUID,
    query: ListQuery = Depends(),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    get_order(db, order_id, actor)
    return list_order_audits(db, actor.organization_id, order_id, query)
