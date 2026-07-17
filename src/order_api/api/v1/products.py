import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from order_api.api.dependencies import require_roles
from order_api.core.database import get_db
from order_api.models import User, UserRole
from order_api.repositories.resources import product_repository
from order_api.schemas import (
    ProductCreate,
    ProductOut,
    ProductPatch,
    StockAdjustment,
)
from order_api.schemas.pagination import ListQuery, Page
from order_api.services import resources as service

router = APIRouter(prefix="/products", tags=["products"])
ALL = (UserRole.owner, UserRole.manager, UserRole.staff, UserRole.viewer)
MANAGERS = (UserRole.owner, UserRole.manager)


@router.get("", response_model=Page[ProductOut])
def list_products(
    query: ListQuery = Depends(),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return service.list_resources(db, product_repository, actor, query)


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*MANAGERS)),
):
    return service.create_product(db, payload, actor)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return service.get_resource(db, product_repository, product_id, actor, "Product")


@router.patch("/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: uuid.UUID,
    payload: ProductPatch,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*MANAGERS)),
):
    return service.update_product(db, product_id, payload, actor)


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*MANAGERS)),
):
    service.deactivate_product(db, product_id, actor)
    return Response(status_code=204)


@router.post("/{product_id}/stock-adjustments", response_model=ProductOut)
def adjust_stock(
    product_id: uuid.UUID,
    payload: StockAdjustment,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*MANAGERS)),
):
    return service.adjust_stock(db, product_id, payload, actor)
