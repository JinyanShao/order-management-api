from sqlalchemy import CheckConstraint, UniqueConstraint

from order_api.models import IdempotencyRecord, Order, OrderItem, Product, User


def constraint_columns(model, constraint_type):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, constraint_type)
    }


def test_unique_and_check_constraints_are_declared():
    assert ("organization_id", "email") in constraint_columns(User, UniqueConstraint)
    assert ("organization_id", "sku") in constraint_columns(Product, UniqueConstraint)
    product_checks = {
        str(constraint.sqltext)
        for constraint in Product.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    item_checks = {
        str(constraint.sqltext)
        for constraint in OrderItem.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "unit_price_cents >= 0" in product_checks
    assert "stock_quantity >= 0" in product_checks
    assert "quantity > 0" in item_checks
    assert "unit_price_cents >= 0" in item_checks


def test_foreign_keys_have_explicit_delete_policies_and_indexes():
    order_id_fk = next(iter(IdempotencyRecord.__table__.c.order_id.foreign_keys))
    assert order_id_fk.ondelete == "CASCADE"
    assert next(iter(Order.__table__.c.customer_id.foreign_keys)).ondelete == "RESTRICT"
    assert next(iter(OrderItem.__table__.c.product_id.foreign_keys)).ondelete == "RESTRICT"
    assert any(index.name == "ix_orders_org_status_created" for index in Order.__table__.indexes)
