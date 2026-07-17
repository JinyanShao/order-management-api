import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from order_api.api.dependencies import require_roles
from order_api.core.database import get_db
from order_api.core.security import hash_password
from order_api.models import User, UserRole
from order_api.repositories.resources import user_repository
from order_api.schemas import UserCreate, UserOut, UserPatch
from order_api.schemas.pagination import ListQuery, Page
from order_api.services import resources as service

router = APIRouter(prefix="/users", tags=["users"])
ALL = (UserRole.owner, UserRole.manager, UserRole.staff, UserRole.viewer)


@router.get("", response_model=Page[UserOut])
def list_users(
    query: ListQuery = Depends(),
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return service.list_resources(db, user_repository, actor, query)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.owner)),
):
    return service.create_user(db, payload, actor, hash_password(payload.password))


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(*ALL)),
):
    return service.get_resource(db, user_repository, user_id, actor, "User")


@router.patch("/{user_id}", response_model=UserOut)
def patch_user(
    user_id: uuid.UUID,
    payload: UserPatch,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.owner)),
):
    password_hash = hash_password(payload.password) if payload.password else None
    return service.update_user(db, user_id, payload, actor, password_hash)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles(UserRole.owner)),
):
    service.deactivate_user(db, user_id, actor)
    return Response(status_code=204)
