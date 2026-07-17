import uuid


def seed_order(client, owner, stock=10, quantity=3):
    customer = client.post(
        "/api/v1/customers", json={"name": "Buyer", "country": "CH"}, headers=owner
    ).json()
    product = client.post(
        "/api/v1/products",
        json={
            "sku": f"SKU-{uuid.uuid4()}",
            "name": "Widget",
            "unit_price_cents": 1250,
            "stock_quantity": stock,
        },
        headers=owner,
    ).json()
    response = client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer["id"],
            "currency": "chf",
            "items": [{"product_id": product["id"], "quantity": quantity}],
        },
        headers={**owner, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json(), product


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200


def test_order_lifecycle_deducts_and_restores_stock(client, owner):
    order, product = seed_order(client, owner)
    assert order["total_amount_cents"] == 3750
    confirmed = client.post(
        f"/api/v1/orders/{order['id']}/confirm",
        json={"version": order["version"]},
        headers=owner,
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_order = confirmed.json()
    current_product = client.get(f"/api/v1/products/{product['id']}", headers=owner).json()
    assert current_product["stock_quantity"] == 7
    cancelled = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": confirmed_order["version"]},
        headers=owner,
    )
    assert cancelled.status_code == 200, cancelled.text
    current_product = client.get(f"/api/v1/products/{product['id']}", headers=owner).json()
    assert current_product["stock_quantity"] == 10


def test_insufficient_stock_rolls_back(client, owner):
    order, product = seed_order(client, owner, stock=1, quantity=2)
    response = client.post(
        f"/api/v1/orders/{order['id']}/confirm",
        json={"version": order["version"]},
        headers=owner,
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK"
    assert error["details"] == {"available": 1, "requested": 2}
    assert error["request_id"]
    current = client.get(f"/api/v1/products/{product['id']}", headers=owner).json()
    assert current["stock_quantity"] == 1


def test_idempotent_order_creation(client, owner):
    customer = client.post("/api/v1/customers", json={"name": "Buyer"}, headers=owner).json()
    product = client.post(
        "/api/v1/products",
        json={"sku": "ONE", "name": "One", "unit_price_cents": 10},
        headers=owner,
    ).json()
    body = {
        "customer_id": customer["id"],
        "currency": "USD",
        "items": [{"product_id": product["id"], "quantity": 1}],
    }
    headers = {**owner, "Idempotency-Key": "same-key"}
    first = client.post("/api/v1/orders", json=body, headers=headers)
    second = client.post("/api/v1/orders", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    body["items"][0]["quantity"] = 2
    assert client.post("/api/v1/orders", json=body, headers=headers).status_code == 409


def test_tenant_isolation(client, owner):
    order, _ = seed_order(client, owner)
    other = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Other",
            "organization_slug": "other",
            "email": "owner@other.example.com",
            "password": "correct-horse-battery-staple",
        },
    ).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/v1/orders/{order['id']}", headers=headers).status_code == 404


def test_optimistic_lock_and_draft_only(client, owner):
    order, _ = seed_order(client, owner)
    assert (
        client.patch(
            f"/api/v1/orders/{order['id']}",
            json={"currency": "EUR", "version": order["version"] + 1},
            headers=owner,
        ).status_code
        == 409
    )
    confirmed = client.post(
        f"/api/v1/orders/{order['id']}/confirm",
        json={"version": order["version"]},
        headers=owner,
    ).json()
    assert (
        client.patch(
            f"/api/v1/orders/{order['id']}",
            json={"currency": "EUR", "version": confirmed["version"]},
            headers=owner,
        ).status_code
        == 409
    )


def test_paginated_list_search_sort_and_tenant_scope(client, owner):
    for name in ("Zulu Buyer", "Alpha Buyer", "Hidden Search"):
        assert (
            client.post("/api/v1/customers", json={"name": name}, headers=owner).status_code == 201
        )
    response = client.get(
        "/api/v1/customers?page=1&page_size=2&sort=name&search=Buyer", headers=owner
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["page"] == 1
    assert page["page_size"] == 2
    assert page["total"] == 2
    assert page["pages"] == 1
    assert [item["name"] for item in page["items"]] == ["Alpha Buyer", "Zulu Buyer"]

    other = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Pagination Other",
            "organization_slug": "pagination-other",
            "email": "pagination@other.example.com",
            "password": "correct-horse-battery-staple",
        },
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get("/api/v1/customers", headers=other_headers).json()["total"] == 0


def test_list_query_rejects_unbounded_page_and_arbitrary_sort(client, owner):
    too_large = client.get("/api/v1/products?page_size=101", headers=owner)
    assert too_large.status_code == 422
    assert too_large.json()["error"]["code"] == "VALIDATION_ERROR"

    bad_sort = client.get("/api/v1/products?sort=password_hash", headers=owner)
    assert bad_sort.status_code == 422
    error = bad_sort.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "password_hash" not in error["details"]["allowed"]


def test_validation_error_has_standard_shape_and_request_id(client):
    response = client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    assert response.headers["X-Request-ID"]
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["request_id"] == response.headers["X-Request-ID"]
