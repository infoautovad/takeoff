from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.database import get_db
from app.models.user import SubscriptionPlan, User
from app.schemas.auth import PLANS, PlanInfo, Token, UserCreate, UserOut
from app.services.activity import log_activity

router = APIRouter()


@router.get("/plans", response_model=list[PlanInfo])
def list_plans() -> list[PlanInfo]:
    return PLANS


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    if payload.plan is None:
        raise HTTPException(status_code=400, detail="A subscription plan must be selected to create an account")

    # Enterprise is contact-sales in product UI; still allow selecting it as the chosen plan.
    if payload.plan not in set(SubscriptionPlan):
        raise HTTPException(status_code=400, detail="Invalid subscription plan")

    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        role=payload.role,
        plan=payload.plan,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_activity(
        db,
        user_id=user.id,
        project_id=None,
        action="user_registered",
        message=f"User {user.email} registered on {user.plan.value} plan",
        entity_type="user",
        entity_id=user.id,
    )

    token = create_access_token(
        user.id,
        extra={"role": user.role.value, "plan": user.plan.value},
    )
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    user = db.scalar(select(User).where(User.email == form_data.username.lower()))
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active or user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive or blocked")

    token = create_access_token(
        user.id,
        extra={"role": user.role.value, "plan": getattr(user.plan, "value", str(user.plan))},
    )
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
