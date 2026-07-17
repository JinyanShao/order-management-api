import concurrent.futures
import threading
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from order_api.core.database import SessionLocal
from order_api.core.security import hash_token
from order_api.models import RefreshToken


def register(client, slug="auth-org", email="owner@auth.example.com"):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": slug,
            "organization_slug": slug,
            "email": email,
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_login_rotation_logout_and_non_disclosure(client):
    tokens = register(client)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "auth-org",
            "email": "owner@auth.example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert login.status_code == 200
    assert login.json()["access_token"] != tokens["access_token"]

    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != tokens["refresh_token"]
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
    new_refresh = rotated.json()["refresh_token"]
    assert (
        client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh}).status_code == 204
    )
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh}).status_code == 401
    )

    unknown = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "auth-org",
            "email": "missing@auth.example.com",
            "password": "wrong-password",
        },
    )
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "auth-org",
            "email": "owner@auth.example.com",
            "password": "wrong-password",
        },
    )
    assert unknown.status_code == wrong_password.status_code == 401
    unknown_error = unknown.json()["error"]
    wrong_error = wrong_password.json()["error"]
    assert {k: v for k, v in unknown_error.items() if k != "request_id"} == {
        k: v for k, v in wrong_error.items() if k != "request_id"
    }


def test_concurrent_refresh_token_rotation_allows_one_success(client):
    tokens = register(client, slug="refresh-race", email="owner@refresh-race.example.com")
    current_user = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    ).json()
    user_id = uuid.UUID(current_user["id"])
    barrier = threading.Barrier(2)

    def rotate_token():
        barrier.wait()
        return client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: rotate_token(), range(2)))

    assert sorted(response.status_code for response in responses) == [200, 401]
    successful = next(response for response in responses if response.status_code == 200)
    rejected = next(response for response in responses if response.status_code == 401)
    assert rejected.json()["error"]["code"] == "INVALID_CREDENTIALS"

    new_refresh_token = successful.json()["refresh_token"]
    now = datetime.now(UTC)
    with SessionLocal() as db:
        active_count = db.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        total_count = db.scalar(
            select(func.count()).select_from(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        active_new_token = db.scalar(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.token_hash == hash_token(new_refresh_token),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )

    assert active_count == 1
    assert total_count == 2
    assert active_new_token is not None


def test_user_permissions_and_customer_product_crud(client, owner):
    viewer = client.post(
        "/api/v1/users",
        json={
            "email": "viewer@example.com",
            "password": "viewer-password",
            "role": "viewer",
        },
        headers=owner,
    )
    assert viewer.status_code == 201
    viewer_login = client.post(
        "/api/v1/auth/login",
        json={
            "organization_slug": "acme",
            "email": "viewer@example.com",
            "password": "viewer-password",
        },
    ).json()
    viewer_headers = {"Authorization": f"Bearer {viewer_login['access_token']}"}
    denied = client.post(
        "/api/v1/products",
        json={"sku": "DENIED", "name": "Denied", "unit_price_cents": 10},
        headers=viewer_headers,
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
    assert client.get("/api/v1/products", headers=viewer_headers).status_code == 200

    user_id = viewer.json()["id"]
    patched_user = client.patch(f"/api/v1/users/{user_id}", json={"role": "staff"}, headers=owner)
    assert patched_user.status_code == 200
    assert client.get(f"/api/v1/users/{user_id}", headers=owner).status_code == 200
    assert client.get("/api/v1/users?search=viewer", headers=owner).json()["total"] == 1

    customer = client.post(
        "/api/v1/customers",
        json={"name": "Initial", "email": "buyer@example.com", "country": "ch"},
        headers=owner,
    )
    assert customer.status_code == 201
    customer_id = customer.json()["id"]
    assert client.get(f"/api/v1/customers/{customer_id}", headers=owner).status_code == 200
    assert (
        client.patch(
            f"/api/v1/customers/{customer_id}", json={"name": "Updated"}, headers=owner
        ).json()["name"]
        == "Updated"
    )

    product = client.post(
        "/api/v1/products",
        json={"sku": "CRUD", "name": "Product", "unit_price_cents": 100},
        headers=owner,
    )
    product_id = product.json()["id"]
    assert client.get(f"/api/v1/products/{product_id}", headers=owner).status_code == 200
    assert (
        client.patch(
            f"/api/v1/products/{product_id}", json={"name": "Renamed"}, headers=owner
        ).json()["name"]
        == "Renamed"
    )
    adjusted = client.post(
        f"/api/v1/products/{product_id}/stock-adjustments",
        json={"quantity_delta": 5, "reason": "delivery"},
        headers=owner,
    )
    assert adjusted.json()["stock_quantity"] == 5
    assert (
        client.post(
            f"/api/v1/products/{product_id}/stock-adjustments",
            json={"quantity_delta": -6, "reason": "invalid"},
            headers=owner,
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/products/{product_id}", headers=owner).status_code == 204
    assert client.delete(f"/api/v1/users/{user_id}", headers=owner).status_code == 204


def test_duplicate_constraints_and_authentication_required(client, owner):
    body = {"sku": "DUPLICATE", "name": "Product", "unit_price_cents": 1}
    assert client.post("/api/v1/products", json=body, headers=owner).status_code == 201
    duplicate = client.post("/api/v1/products", json=body, headers=owner)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RESOURCE_CONFLICT"
    missing_auth = client.get("/api/v1/orders")
    assert missing_auth.status_code == 401
    assert missing_auth.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_cors_and_trusted_host_are_explicit(client):
    allowed = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    rejected_origin = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in rejected_origin.headers
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
