from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from order_api.models import Organization, RefreshToken, User


def find_login_user(db: Session, organization_slug: str, email: str) -> User | None:
    return db.scalar(
        select(User)
        .join(Organization)
        .where(
            Organization.slug == organization_slug,
            User.email == email,
            User.is_active.is_(True),
        )
    )


def find_refresh_token(
    db: Session,
    token_hash: str,
    now: datetime,
    *,
    lock: bool = False,
) -> RefreshToken | None:
    statement = select(RefreshToken).where(
        RefreshToken.token_hash == token_hash,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > now,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def find_token_for_logout(db: Session, token_hash: str) -> RefreshToken | None:
    return db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
