import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from order_api.api.dependencies import require_roles
from order_api.core.database import get_db
from order_api.models import User, UserRole
from order_api.repositories.resources import customer_repository
from order_api.schemas import CustomerCreate, CustomerOut, CustomerPatch
from order_api.schemas.pagination import ListQuery, Page
from order_api.services import resources as service

router = APIRouter(prefix="/customers", tags=["customers"])
ALL = (UserRole.owner, UserRole.manager, UserRole.staff, UserRole.viewer)
WRITERS = (UserRole.owner, UserRole.manager, UserRole.staff)


@router.get("", response_model=Page[CustomerOut])
def list_customers(
    query: ListQuery = Depends(),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return service.list_resources(db, customer_repository, actor, query)


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*WRITERS)),
):
    return service.create_customer(db, payload, actor)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return service.get_resource(db, customer_repository, customer_id, actor, "Customer")


@router.patch("/{customer_id}", response_model=CustomerOut)
def patch_customer(
    customer_id: uuid.UUID,
    payload: CustomerPatch,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*WRITERS)),
):
    return service.update_customer(db, customer_id, payload, actor)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(
    customer_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.owner, UserRole.manager)),
):
    service.delete_customer(db, customer_id, actor)
    return Response(status_code=204)
