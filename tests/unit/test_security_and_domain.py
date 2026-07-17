import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest

from order_api.core.config import get_settings
from order_api.core.exceptions import AppError
from order_api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)
from order_api.models import OrderStatus
from order_api.services.orders import check_version, ensure_draft, recalculate


def test_password_hash_and_token_round_trip():
    password_hash = hash_password("correct-horse-battery-staple")
    assert password_hash != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", password_hash)
    assert not verify_password("wrong-password", password_hash)

    user_id = uuid.uuid4()
    access = create_access_token(user_id)
    assert decode_access_token(access) == user_id
    raw, digest, expires_at = create_refresh_token()
    assert digest == hash_token(raw)
    assert raw != digest
    assert expires_at > datetime.now(UTC)


def test_access_token_rejects_wrong_type_and_expiration():
    settings = get_settings()
    wrong_type = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "refresh",
            "exp": datetime.now(UTC) + timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(wrong_type)
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "type": "access",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired)


def test_order_amount_and_state_guards():
    order = SimpleNamespace(
        items=[SimpleNamespace(line_total_cents=250), SimpleNamespace(line_total_cents=750)],
        total_amount_cents=0,
        version=2,
        status=OrderStatus.draft,
    )
    recalculate(order)
    assert order.total_amount_cents == 1000
    assert order.version == 3
    check_version(order, 3)
    ensure_draft(order)

    with pytest.raises(AppError) as version_error:
        check_version(order, 2)
    assert version_error.value.code == "OPTIMISTIC_LOCK_CONFLICT"
    order.status = OrderStatus.shipped
    with pytest.raises(AppError) as state_error:
        ensure_draft(order)
    assert state_error.value.code == "INVALID_ORDER_TRANSITION"
