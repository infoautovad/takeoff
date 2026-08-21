"""Bootstrap the portal admin account used by /backend Training Lab."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import SubscriptionPlan, User, UserRole

# Dedicated portal admin (homepage Admin sign-in). Not for public registration.
PORTAL_ADMIN_NAME = "agastya"
PORTAL_ADMIN_EMAIL = "agastya@autovad.com"
PORTAL_ADMIN_PASSWORD = "12345678"


def ensure_portal_admin(db: Session) -> User:
    """Create or refresh the fixed portal admin credentials."""
    user = db.scalar(select(User).where(User.email == PORTAL_ADMIN_EMAIL))
    if user is None:
        # Also reclaim by name if an older row exists
        user = db.scalar(
            select(User).where(User.full_name.ilike(PORTAL_ADMIN_NAME), User.role == UserRole.ADMIN)
        )

    if user is None:
        user = User(
            email=PORTAL_ADMIN_EMAIL,
            full_name=PORTAL_ADMIN_NAME,
            hashed_password=hash_password(PORTAL_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            plan=SubscriptionPlan.ENTERPRISE,
            is_active=True,
            is_blocked=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    changed = False
    if user.full_name.strip().lower() != PORTAL_ADMIN_NAME:
        user.full_name = PORTAL_ADMIN_NAME
        changed = True
    if user.email.lower() != PORTAL_ADMIN_EMAIL:
        user.email = PORTAL_ADMIN_EMAIL
        changed = True
    if user.role != UserRole.ADMIN:
        user.role = UserRole.ADMIN
        changed = True
    if not verify_password(PORTAL_ADMIN_PASSWORD, user.hashed_password):
        user.hashed_password = hash_password(PORTAL_ADMIN_PASSWORD)
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if user.is_blocked:
        user.is_blocked = False
        changed = True
    if changed:
        db.commit()
        db.refresh(user)
    return user


def find_portal_admin(db: Session, admin_name: str) -> User | None:
    name = (admin_name or "").strip().lower()
    if not name:
        return None
    user = db.scalar(
        select(User).where(
            User.role == UserRole.ADMIN,
            User.full_name.ilike(name),
        )
    )
    if user:
        return user
    # Allow typing the local-part of the seeded email
    return db.scalar(
        select(User).where(
            User.role == UserRole.ADMIN,
            User.email.ilike(f"{name}@%"),
        )
    )
