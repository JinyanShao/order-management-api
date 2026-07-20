# Order Management API

[![CI](https://github.com/JinyanShao/order-management-api/actions/workflows/ci.yml/badge.svg)](https://github.com/JinyanShao/order-management-api/actions/workflows/ci.yml)
![Coverage](https://img.shields.io/badge/coverage-%E2%89%A590%25-brightgreen)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

A multi-tenant order operations backend that turns business workflows into reliable, observable,
and automatable software.

## 1. Project overview

Order Management API is a single deployable backend for organizations that manage users,
customers, products, inventory and orders. It provides JWT authentication, role-based access,
tenant isolation, transactional inventory handling, audit trails and concurrency protection.
The current API version is `v1.0.0`.

Interactive OpenAPI documentation is available at `/docs`; health endpoints are exposed at
`/health` and `/ready`.

## 2. Business problem

Order processing is more than CRUD. Confirming an order must reserve stock atomically, concurrent
requests must not oversell, cancellation may need to restore inventory, and every operation must
remain inside the authenticated organization. This project centralizes those rules and exposes a
consistent HTTP contract suitable for internal tools or future frontend clients.

The product direction is organized around four business goals:

1. Reduce order failures caused by stock shortages, duplicate requests and invalid state changes.
2. Automatically identify orders that require human attention.
3. Give operations teams actionable business metrics.
4. Preserve a complete, explainable record of business decisions.

## 3. Core features

- Organization-based multi-tenancy derived from the authenticated user.
- Owner, manager, staff and viewer RBAC.
- Short-lived JWT access tokens and rotating, revocable refresh tokens.
- Customer and product management with tenant-scoped uniqueness.
- Explicit order state machine with transactional inventory changes.
- Optimistic order locking through `version`.
- PostgreSQL row locking during stock reservation and restoration.
- `Idempotency-Key` support for order creation.
- Unified pagination, filtering, search and safe sorting.
- Audit logs for order state and inventory changes.
- Standard error envelope and request ID propagation.
- Structured JSON request logs and database-aware readiness checks.

These capabilities remain the foundation of the next version. The existing order flow already
provides atomic inventory deduction, inventory restoration on cancellation, state-transition
validation and server-side amount calculation. The next version adds operational depth to this
reliable core rather than replacing it.

## 4. Architecture

The service follows a router → service → repository flow:

```text
HTTP request
    │
    ▼
Router        input, dependencies, status code, serialization
    │
    ▼
Service       business rules, permissions, state machine, transaction boundary
    │
    ▼
Repository    tenant-scoped SQL, pagination, persistence and row locking
    │
    ▼
PostgreSQL
```

Source layout:

```text
src/order_api/
├── api/             # dependencies and versioned routers
├── core/            # configuration, database, security, errors and logging
├── middleware/      # request context and structured request logging
├── models/          # SQLAlchemy models
├── repositories/    # queries, pagination and locking
├── schemas/         # Pydantic request/response schemas
├── services/        # authentication, resources and order domain
└── main.py
```

## 5. Domain model

- `Organization`: tenant boundary and unique slug.
- `User`: belongs to one organization; email is unique within that organization.
- `Customer`: organization-owned order customer.
- `Product`: organization-owned SKU, integer-cent price, stock and active state.
- `Order`: customer, state, currency, calculated total, version and creator.
- `OrderItem`: product snapshot price, quantity and calculated line total.
- `AuditLog`: actor, entity, action and JSON change details.
- `RefreshToken`: hashed rotating token, expiry and revocation timestamp.
- `IdempotencyRecord`: request hash and resulting order for a scoped key.

The schema includes foreign keys, unique constraints, check constraints, indexes and explicit
delete policies. Money is represented as integer cents.

## 6. Order state machine

```text
draft ──► confirmed ──► processing ──► shipped
  │           │              │
  └───────────┴──────────────┴──────► cancelled
```

- Only draft orders can change customer, currency or items.
- Confirmation locks product rows, verifies stock and deducts inventory in one transaction.
- Cancelling confirmed or processing orders restores inventory.
- Shipped orders cannot be cancelled.
- Totals and line totals are always calculated by the server.
- Every mutation or transition validates the submitted order version.

## 7. Authorization matrix

| Operation | Owner | Manager | Staff | Viewer |
|---|:---:|:---:|:---:|:---:|
| Manage users | ✓ |  |  |  |
| Manage products and stock | ✓ | ✓ |  |  |
| Create customers | ✓ | ✓ | ✓ |  |
| Create or modify orders | ✓ | ✓ | ✓ |  |
| Delete drafts | ✓ | ✓ |  |  |
| View tenant data | ✓ | ✓ | ✓ | ✓ |

RBAC does not replace tenant filtering: every business query independently applies the current
user's `organization_id`.

## 8. API overview

| Area | Endpoints |
|---|---|
| Health | `GET /health`, `GET /ready` |
| Authentication | register, login, refresh, logout, current user |
| Users | list, create, retrieve, update, deactivate |
| Customers | list, create, retrieve, update, delete |
| Products | list, create, retrieve, update, deactivate, stock adjustment |
| Orders | list, create, retrieve, update, delete draft, item operations |
| Transitions | confirm, start processing, ship, cancel |
| Audit | tenant audit list and order audit list |

All API resources are under `/api/v1`. List endpoints accept `page`, `page_size`, `sort`,
`status`, `search`, `created_from` and `created_to`. Page size is capped at 100 and each resource
has an explicit sorting allowlist.

## 9. Local installation

Requirements: Python 3.12 and a running PostgreSQL 16 instance.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
uvicorn order_api.main:app --reload
```

Open `http://localhost:8000/docs` after startup.

## 10. Environment variables

| Variable | Required | Default / purpose |
|---|:---:|---|
| `DATABASE_URL` | Yes | SQLAlchemy PostgreSQL URL |
| `JWT_SECRET_KEY` | Yes | At least 32 characters; no application default |
| `JWT_ALGORITHM` | No | `HS256` |
| `JWT_ISSUER` | No | `order-management-api` |
| `JWT_AUDIENCE` | No | `order-management-api-clients` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `30` |
| `CORS_ORIGINS` | No | JSON list; local frontend origin by default |
| `TRUSTED_HOSTS` | No | JSON list of accepted Host values |

Never commit `.env`. Generate a unique secret for every deployed environment.

## 11. Database migrations

Apply all migrations:

```bash
alembic upgrade head
```

Verify that SQLAlchemy metadata has no ungenerated changes:

```bash
alembic check
```

Create a migration after changing models:

```bash
alembic revision --autogenerate -m "describe change"
```

Migrations run automatically before Uvicorn starts in the Docker API container.

## 12. Docker usage

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs -f api
```

Compose contains only `api` and `postgres`. Both have health checks, PostgreSQL uses the persistent
`postgres_data` volume, and the API runs as the non-root `order-api` user.

Stop containers without deleting database data:

```bash
docker compose down
```

## 13. Testing

The PostgreSQL test database name must end with `_test`; the suite refuses other PostgreSQL
database names to protect development data.

```bash
export DATABASE_URL=postgresql+psycopg://orders:orders@localhost:5432/orders_test
export JWT_SECRET_KEY=test-secret-key-with-at-least-32-characters
pytest --cov=order_api --cov-report=term-missing --cov-fail-under=90
ruff check src tests
ruff format --check src tests
```

The suite covers unit, integration and concurrent confirmation behavior. Current measured coverage
is above the enforced 90% threshold.

## 14. Example requests

Register an organization owner and capture the returned access token. The example uses `jq` to
extract response fields:

```bash
AUTH_RESPONSE="$(curl -sS -X POST http://localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{
    "organization_name": "Acme",
    "organization_slug": "acme",
    "email": "owner@acme.example.com",
    "password": "Example-Only-Password-2026!"
  }')"
ACCESS_TOKEN="$(printf '%s' "$AUTH_RESPONSE" | jq -r '.access_token')"
```

Create a customer and product, then create an order with their returned IDs:

```bash
CUSTOMER_ID="$(curl -sS -X POST http://localhost:8000/api/v1/customers \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Example Customer","country":"CH"}' | jq -r '.id')"

PRODUCT_ID="$(curl -sS -X POST http://localhost:8000/api/v1/products \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-1001","name":"Example Product","unit_price_cents":2500,"stock_quantity":10}' \
  | jq -r '.id')"

curl -X POST http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Idempotency-Key: checkout-2026-0001' \
  -H 'Content-Type: application/json' \
  -d "{
    \"customer_id\": \"$CUSTOMER_ID\",
    \"currency\": \"CHF\",
    \"items\": [
      {\"product_id\": \"$PRODUCT_ID\", \"quantity\": 2}
    ]
  }"
```

Safely list orders:

```bash
curl 'http://localhost:8000/api/v1/orders?page=1&page_size=20&status=confirmed&sort=-created_at' \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

## 15. Error model

Every application, validation and HTTP error uses the same envelope. `X-Request-ID` is also
returned as a response header.

```json
{
  "error": {
    "code": "INSUFFICIENT_STOCK",
    "message": "Insufficient stock for product SKU-1001.",
    "details": {"available": 3, "requested": 5},
    "request_id": "8a0d5a1c-..."
  }
}
```

Primary codes include `VALIDATION_ERROR`, `AUTHENTICATION_REQUIRED`, `INVALID_CREDENTIALS`,
`PERMISSION_DENIED`, `RESOURCE_NOT_FOUND`, `RESOURCE_CONFLICT`, `INVALID_ORDER_TRANSITION`,
`INSUFFICIENT_STOCK`, `IDEMPOTENCY_CONFLICT` and `OPTIMISTIC_LOCK_CONFLICT`.

## 16. Security decisions

- Passwords use Argon2 and are never stored or logged in plaintext.
- Access tokens are signed JWTs with expiry, type, subject, unique `jti`, issuer and audience claims.
- Refresh tokens are opaque random values; only SHA-256 digests are stored.
- Refresh tokens rotate on use and old tokens are immediately revoked.
- Authentication failures do not reveal whether an organization or user exists.
- CORS and Trusted Host policies are explicit and environment-configurable.
- Secrets are loaded from environment variables, not committed source defaults.
- Structured logs use controlled fields and omit bodies, passwords and tokens.

## 17. Concurrency and idempotency

Confirmation acquires PostgreSQL `SELECT ... FOR UPDATE` locks on product rows in deterministic ID
order. Stock validation and deduction occur in the same transaction, so concurrent confirmations
cannot make inventory negative. A PostgreSQL concurrency test confirms that when stock only covers
one of two simultaneous orders, exactly one succeeds.

Order mutations use an optimistic `version`. Stale writers receive
`OPTIMISTIC_LOCK_CONFLICT`. Order creation scopes `Idempotency-Key` to the current user and
organization, hashes the request body, returns the original order for identical retries and rejects
key reuse with a different body.

## 18. Limitations

- Single-region, single PostgreSQL deployment; no multi-region conflict resolution.
- No frontend, GraphQL, message broker, background worker or Kubernetes manifests.
- Inventory is reserved at confirmation rather than through expiring reservations.
- Refresh-token cleanup currently relies on database retention rather than a scheduled job.
- Request body size is not yet enforced inside the application.
- Offset pagination is appropriate for current scale but not optimized for very large datasets.

## 19. Roadmap

Implementation phases completed for v1.0.0:

- [x] **Phase 1 — Foundation:** structure, configuration, PostgreSQL, SQLAlchemy, Alembic, health
  endpoints and CI.
- [x] **Phase 2 — Authentication:** organizations, users, register/login, access/refresh tokens and
  RBAC.
- [x] **Phase 3 — Business Resources:** customers, products, pagination, filtering and tenant
  isolation.
- [x] **Phase 4 — Order Domain:** orders, items, amount calculation, lifecycle, inventory reservation
  and transactions.
- [x] **Phase 5 — Reliability:** audit logs, idempotency, optimistic locking, concurrent stock test
  and standardized errors.
- [x] **Phase 6 — Release:** Docker, README, coverage enforcement, security review and v1.0.0 release
  readiness.

Post-v1 candidates:

- **Order Exceptions:** a tenant-scoped operations queue that identifies order problems, assigns
  responsibility and tracks each issue through resolution. Planned exception types are
  `payment_pending`, `insufficient_stock`, `inventory_changed`,
  `customer_information_incomplete`, `processing_overdue`, `shipment_overdue` and
  `manual_review_required`.
  - Each exception links to an order and records its organization, type, severity (`low`, `medium`,
    `high` or `critical`), reason, current assignee, creation time, resolution time and resolution
    note.
  - Its lifecycle is `open`, `acknowledged`, `resolved` or `dismissed`.
  - The module provides explicit problem detection, ownership and a closed-loop operational
    workflow instead of requiring staff to discover issues manually in order lists.
- **Inventory Reservations:** time-limited stock holds for carts, quotations, manual reviews and
  payment-waiting workflows. Creating an order may reserve inventory before confirmation rather
  than deducting it immediately.
  - Every reservation has an expiration time and belongs to a specific order and product.
  - Confirmation converts reserved quantities into committed inventory deductions.
  - Cancellation releases active reservations, while unconfirmed reservations are released
    automatically after expiration.
  - Repeated requests for the same order must not reserve inventory more than once.
  - Every reservation, conversion, release and expiration is written to the audit log.
  - Reservation and release operations remain transactionally safe under concurrent requests and
    preserve consistent available-stock calculations.
  - The module introduces a justified background task, time-driven business rules, idempotent
    operations and concurrent transaction handling without changing the existing inventory safety
    guarantees.
- **Automation Rules:** simple, administrator-managed rules that safely automate repeated
  operational decisions. V2 intentionally supports only four rule templates:
  1. Mark high-value orders for manual review.
  2. Create an inventory exception when stock falls below a configured threshold.
  3. Create an overdue exception when an order remains in `processing` beyond a configured period.
  4. Move an eligible order into `processing` automatically.
  - Each rule records its name, trigger event, structured conditions, action, enabled state,
    priority, last run time and most recent execution result.
  - Conditions and actions use finite, validated schemas. Users cannot submit executable code or
    define an unrestricted domain-specific language.
  - The module is deliberately not a general-purpose rules engine. Its scope stays small enough to
    audit, test and explain every supported decision path.
  - This capability demonstrates how repeated business decisions can be identified and automated
    without weakening operational control or system predictability.
- Reverse-proxy and application-level request body size limits.
- Keyset pagination for high-volume datasets.
- Scheduled cleanup for expired refresh tokens and idempotency records.
- Refresh-token families with reuse detection and family-wide revocation.
- OpenTelemetry tracing when distributed deployment makes it useful.

## 20. License

Released under the MIT License. See [LICENSE](LICENSE).
