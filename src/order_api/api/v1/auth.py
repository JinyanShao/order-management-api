from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from order_api.api.dependencies import get_current_user
from order_api.core.database import get_db
from order_api.models import User
from order_api.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from order_api.services import auth as service

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=TokenPair, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    return service.register(db, payload)


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return service.login(db, payload)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    return service.refresh(db, payload.refresh_token)


@router.post("/logout", status_code=204)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    service.logout(db, payload.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
