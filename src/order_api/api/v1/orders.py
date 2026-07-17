import uuid

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from order_api.api.dependencies import require_roles
from order_api.core.database import get_db
from order_api.models import OrderStatus, User, UserRole
from order_api.repositories.resources import order_repository
from order_api.schemas import (
    OrderCreate,
    OrderItemCreate,
    OrderItemPatch,
    OrderOut,
    OrderPatch,
    VersionRequest,
)
from order_api.schemas.pagination import ListQuery, Page
from order_api.services import orders as service
from order_api.services.resources import list_resources

router = APIRouter(prefix="/orders", tags=["orders"])
ALL = (UserRole.owner, UserRole.manager, UserRole.staff, UserRole.viewer)
WRITERS = (UserRole.owner, UserRole.manager, UserRole.staff)


@router.get("", response_model=Page[OrderOut])
def list_orders(
    query: ListQuery = Depends(),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return list_resources(db, order_repository, actor, query)


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    payload: OrderCreate,
    idempotency_key: str = Header(min_length=1, max_length=255, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*WRITERS)),
):
    return service.create_order(db, payload, actor, idempotency_key)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return service.get_order(db, order_id, actor)


@router.patch("/{order_id}", response_model=OrderOut)
def patch_order(
    order_id: uuid.UUID,
    payload: OrderPatch,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*WRITERS)),
):
    return service.update_order(db, order_id, payload, actor)


@router.delete("/{order_id}", status_code=204)
def delete_order(
    order_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.owner, UserRole.manager)),
):
    service.delete_draft(db, order_id, version, actor)
    return Response(status_code=204)


@router.post("/{order_id}/items", response_model=OrderOut)
def add_item(
    order_id: uuid.UUID,
    payload: OrderItemCreate,
    version: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*WRITERS)),
):
    return service.add_item(db, order_id, payload, version, actor)


@router.patch("/{order_id}/items/{item_id}", response_model=OrderOut)
def patch_item(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: OrderItemPatch,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*WRITERS)),
):
    return service.update_item(db, order_id, item_id, payload, actor)


@router.delete("/{order_id}/items/{item_id}", response_model=OrderOut)
def delete_item(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    version: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*WRITERS)),
):
    return service.delete_item(db, order_id, item_id, version, actor)


def transition_endpoint(target: OrderStatus):
    def endpoint(
        order_id: uuid.UUID,
        payload: VersionRequest,
        db: Session = Depends(get_db),
        actor: User = Depends(require_roles(*WRITERS)),
    ):
        return service.transition_order(db, order_id, actor, payload.version, target)

    return endpoint


router.post("/{order_id}/confirm", response_model=OrderOut)(
    transition_endpoint(OrderStatus.confirmed)
)
router.post("/{order_id}/start-processing", response_model=OrderOut)(
    transition_endpoint(OrderStatus.processing)
)
router.post("/{order_id}/ship", response_model=OrderOut)(transition_endpoint(OrderStatus.shipped))
router.post("/{order_id}/cancel", response_model=OrderOut)(
    transition_endpoint(OrderStatus.cancelled)
)
