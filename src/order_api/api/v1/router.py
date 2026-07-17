from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from order_api.api.v1 import audit_logs, auth, customers, orders, products, users

router = APIRouter()
for module in (auth, users, customers, products, orders, audit_logs):
    router.include_router(module.router)


def readiness(db: Session) -> bool:
    db.execute(text("SELECT 1"))
    return True
