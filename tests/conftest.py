import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://orders:orders@localhost:5432/orders_test"
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-at-least-32-characters")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from order_api.core.database import Base, engine
from order_api.main import app

test_database_url = make_url(os.environ["DATABASE_URL"])
if test_database_url.get_backend_name() == "postgresql" and not (
    test_database_url.database or ""
).endswith("_test"):
    raise RuntimeError("Tests require a PostgreSQL database whose name ends with '_test'")


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def owner(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Acme",
            "organization_slug": "acme",
            "email": "owner@acme.example.com",
            "password": "correct-horse-battery-staple",
        },
    )
    assert response.status_code == 201, response.text
    tokens = response.json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}
