from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from order_api.core.exceptions import AppError, conflict
from order_api.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from order_api.models import Organization, RefreshToken, User, UserRole
from order_api.repositories.auth_repository import (
    find_login_user,
    find_refresh_token,
    find_token_for_logout,
)
from order_api.schemas import LoginRequest, RegisterRequest, TokenPair


def issue_token_pair(db: Session, user: User) -> TokenPair:
    raw, digest, expires_at = create_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=digest, expires_at=expires_at))
    db.commit()
    return TokenPair(access_token=create_access_token(user.id), refresh_token=raw)


def register(db: Session, payload: RegisterRequest) -> TokenPair:
    try:
        organization = Organization(name=payload.organization_name, slug=payload.organization_slug)
        db.add(organization)
        db.flush()
        user = User(
            organization_id=organization.id,
            email=payload.email.lower(),
            password_hash=hash_password(payload.password),
            role=UserRole.owner,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise conflict("Organization slug already exists.") from None
    return issue_token_pair(db, user)


def login(db: Session, payload: LoginRequest) -> TokenPair:
    user = find_login_user(db, payload.organization_slug, payload.email.lower())
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid credentials.", status_code=401)
    return issue_token_pair(db, user)


def refresh(db: Session, raw_token: str) -> TokenPair:
    now = datetime.now(UTC)
    token = find_refresh_token(db, hash_token(raw_token), now)
    if token is None:
        raise AppError("INVALID_CREDENTIALS", "Invalid refresh token.", status_code=401)
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise AppError("INVALID_CREDENTIALS", "Invalid refresh token.", status_code=401)
    token.revoked_at = now
    db.flush()
    return issue_token_pair(db, user)


def logout(db: Session, raw_token: str) -> None:
    token = find_token_for_logout(db, hash_token(raw_token))
    if token and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        db.commit()
