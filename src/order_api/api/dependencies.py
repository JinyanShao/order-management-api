import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from order_api.core.database import get_db
from order_api.core.exceptions import authentication_required, not_found, permission_denied
from order_api.core.security import decode_access_token
from order_api.models import User, UserRole

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    error = authentication_required("Invalid or expired access token.")
    if credentials is None:
        raise error
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.PyJWTError, ValueError):
        raise error from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise error
    request.state.user_id = str(user.id)
    request.state.organization_id = str(user.organization_id)
    return user


def require_roles(*roles: UserRole) -> Callable:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise permission_denied()
        return user

    return dependency


def tenant_get(db: Session, model: type, object_id: uuid.UUID, user: User):
    obj = db.get(model, object_id)
    if obj is None or obj.organization_id != user.organization_id:
        raise not_found(model.__name__)
    return obj
