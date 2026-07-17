"""Add order constraints, indexes, and explicit delete policies."""

from alembic import op

revision = "0002_constraints"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_orders_total_nonnegative'
          ) THEN
            ALTER TABLE orders ADD CONSTRAINT ck_orders_total_nonnegative
              CHECK (total_amount_cents >= 0);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_orders_version_positive'
          ) THEN
            ALTER TABLE orders ADD CONSTRAINT ck_orders_version_positive CHECK (version > 0);
          END IF;
        END $$;
        CREATE INDEX IF NOT EXISTS ix_orders_org_status_created
          ON orders (organization_id, status, created_at);
        """
    )
    op.drop_constraint(
        "idempotency_records_order_id_fkey", "idempotency_records", type_="foreignkey"
    )
    op.create_foreign_key(
        "idempotency_records_order_id_fkey",
        "idempotency_records",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )
    policies = (
        ("orders_customer_id_fkey", "orders", "customers", ["customer_id"], "RESTRICT"),
        ("orders_created_by_fkey", "orders", "users", ["created_by"], "RESTRICT"),
        ("order_items_product_id_fkey", "order_items", "products", ["product_id"], "RESTRICT"),
        ("audit_logs_actor_id_fkey", "audit_logs", "users", ["actor_id"], "RESTRICT"),
        (
            "idempotency_records_organization_id_fkey",
            "idempotency_records",
            "organizations",
            ["organization_id"],
            "CASCADE",
        ),
        (
            "idempotency_records_user_id_fkey",
            "idempotency_records",
            "users",
            ["user_id"],
            "CASCADE",
        ),
    )
    for name, source, target, columns, ondelete in policies:
        op.drop_constraint(name, source, type_="foreignkey")
        op.create_foreign_key(name, source, target, columns, ["id"], ondelete=ondelete)


def downgrade() -> None:
    policies = (
        ("orders_customer_id_fkey", "orders", "customers", ["customer_id"]),
        ("orders_created_by_fkey", "orders", "users", ["created_by"]),
        ("order_items_product_id_fkey", "order_items", "products", ["product_id"]),
        ("audit_logs_actor_id_fkey", "audit_logs", "users", ["actor_id"]),
        (
            "idempotency_records_organization_id_fkey",
            "idempotency_records",
            "organizations",
            ["organization_id"],
        ),
        ("idempotency_records_user_id_fkey", "idempotency_records", "users", ["user_id"]),
    )
    for name, source, target, columns in policies:
        op.drop_constraint(name, source, type_="foreignkey")
        op.create_foreign_key(name, source, target, columns, ["id"])
    op.drop_constraint(
        "idempotency_records_order_id_fkey", "idempotency_records", type_="foreignkey"
    )
    op.create_foreign_key(
        "idempotency_records_order_id_fkey",
        "idempotency_records",
        "orders",
        ["order_id"],
        ["id"],
    )
    op.execute("DROP INDEX IF EXISTS ix_orders_org_status_created")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_version_positive")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS ck_orders_total_nonnegative")
