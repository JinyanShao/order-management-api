import concurrent.futures
import threading
import uuid


def create_customer_product(client, headers, *, sku, stock=10):
    customer = client.post(
        "/api/v1/customers", json={"name": f"Buyer {sku}"}, headers=headers
    ).json()
    product = client.post(
        "/api/v1/products",
        json={
            "sku": sku,
            "name": f"Product {sku}",
            "unit_price_cents": 500,
            "stock_quantity": stock,
        },
        headers=headers,
    ).json()
    return customer, product


def create_order(client, headers, customer_id, product_id, *, quantity=1, key=None):
    response = client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer_id,
            "currency": "USD",
            "items": [{"product_id": product_id, "quantity": quantity}],
        },
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_order_items_full_lifecycle_audit_and_delete(client, owner):
    customer, first_product = create_customer_product(client, owner, sku="LIFE-1")
    second_product = client.post(
        "/api/v1/products",
        json={
            "sku": "LIFE-2",
            "name": "Second",
            "unit_price_cents": 250,
            "stock_quantity": 10,
        },
        headers=owner,
    ).json()
    order = create_order(client, owner, customer["id"], first_product["id"], key="lifecycle")
    added = client.post(
        f"/api/v1/orders/{order['id']}/items?version={order['version']}",
        json={"product_id": second_product["id"], "quantity": 2},
        headers=owner,
    )
    assert added.status_code == 200, added.text
    order = added.json()
    second_item = next(
        item for item in order["items"] if item["product_id"] == second_product["id"]
    )
    patched = client.patch(
        f"/api/v1/orders/{order['id']}/items/{second_item['id']}",
        json={"quantity": 3, "version": order["version"]},
        headers=owner,
    )
    assert patched.status_code == 200
    order = patched.json()
    assert order["total_amount_cents"] == 1250
    first_item = next(item for item in order["items"] if item["product_id"] == first_product["id"])
    deleted = client.delete(
        f"/api/v1/orders/{order['id']}/items/{first_item['id']}?version={order['version']}",
        headers=owner,
    )
    order = deleted.json()
    assert order["total_amount_cents"] == 750

    confirmed = client.post(
        f"/api/v1/orders/{order['id']}/confirm",
        json={"version": order["version"]},
        headers=owner,
    ).json()
    processing = client.post(
        f"/api/v1/orders/{order['id']}/start-processing",
        json={"version": confirmed["version"]},
        headers=owner,
    ).json()
    shipped = client.post(
        f"/api/v1/orders/{order['id']}/ship",
        json={"version": processing["version"]},
        headers=owner,
    ).json()
    invalid_cancel = client.post(
        f"/api/v1/orders/{order['id']}/cancel",
        json={"version": shipped["version"]},
        headers=owner,
    )
    assert invalid_cancel.status_code == 409
    assert invalid_cancel.json()["error"]["code"] == "INVALID_ORDER_TRANSITION"

    audits = client.get(f"/api/v1/orders/{order['id']}/audit-logs?sort=created_at", headers=owner)
    assert audits.status_code == 200
    assert audits.json()["total"] >= 7
    assert client.get("/api/v1/audit-logs?search=status", headers=owner).json()["total"] >= 3

    draft = create_order(
        client, owner, customer["id"], first_product["id"], key="delete-idempotent-draft"
    )
    assert (
        client.delete(
            f"/api/v1/orders/{draft['id']}?version={draft['version']}", headers=owner
        ).status_code
        == 204
    )


def test_customer_delete_rollback_when_referenced(client, owner):
    customer, product = create_customer_product(client, owner, sku="ROLLBACK")
    create_order(client, owner, customer["id"], product["id"])
    response = client.delete(f"/api/v1/customers/{customer['id']}", headers=owner)
    assert response.status_code == 409
    assert client.get(f"/api/v1/customers/{customer['id']}", headers=owner).status_code == 200


def test_concurrent_confirmation_never_oversells(client, owner):
    customer, product = create_customer_product(client, owner, sku="CONCURRENT", stock=1)
    first = create_order(client, owner, customer["id"], product["id"], key="concurrent-1")
    second = create_order(client, owner, customer["id"], product["id"], key="concurrent-2")
    barrier = threading.Barrier(2)

    def confirm(order):
        barrier.wait()
        return client.post(
            f"/api/v1/orders/{order['id']}/confirm",
            json={"version": order["version"]},
            headers=owner,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(confirm, (first, second)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    failed = next(response for response in responses if response.status_code == 409)
    assert failed.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    remaining = client.get(f"/api/v1/products/{product['id']}", headers=owner).json()
    assert remaining["stock_quantity"] == 0
