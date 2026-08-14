from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.user import SubscriptionPlan, UserRole

_PASSWORD_RULES = (
    (r".{8,}", "at least 8 characters"),
    (r"[A-Z]", "one uppercase letter"),
    (r"[a-z]", "one lowercase letter"),
    (r"[0-9]", "one number"),
    (r"[^A-Za-z0-9]", "one special character"),
)


def validate_strong_password(password: str) -> str:
    missing = [label for pattern, label in _PASSWORD_RULES if not re.search(pattern, password)]
    if missing:
        raise ValueError("Password must include " + ", ".join(missing) + ".")
    return password


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    role: UserRole
    plan: SubscriptionPlan

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if len(cleaned) < 2:
            raise ValueError("Full name is required")
        return cleaned

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        return validate_strong_password(value)

    @field_validator("plan")
    @classmethod
    def plan_required(cls, value: SubscriptionPlan) -> SubscriptionPlan:
        if value is None:
            raise ValueError("A subscription plan must be selected")
        return value

    @model_validator(mode="after")
    def passwords_must_match(self) -> "UserCreate":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    plan: SubscriptionPlan
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PlanInfo(BaseModel):
    id: SubscriptionPlan
    name: str
    price_label: str
    blurb: str
    features: list[str]
    recommended: bool = False
    cta: str


PLANS: list[PlanInfo] = [
    PlanInfo(
        id=SubscriptionPlan.STARTER,
        name="Starter",
        price_label="$59 / month",
        blurb="For individual estimators beginning with AI-assisted takeoffs.",
        features=[
            "100 AI credits monthly",
            "PDF plan takeoffs only",
            "Bid-item template matching",
            "No credit rollover",
        ],
        cta="Choose Starter",
    ),
    PlanInfo(
        id=SubscriptionPlan.PROFESSIONAL,
        name="Professional",
        price_label="$199 / month",
        blurb="For civil estimators producing frequent review-ready quantity takeoffs.",
        features=[
            "500 AI credits monthly",
            "Support for PDF, DWG, DXF, and LandXML",
            "Source notes and confidence flags",
            "90-day credit rollover",
        ],
        recommended=True,
        cta="Choose Professional",
    ),
    PlanInfo(
        id=SubscriptionPlan.BUSINESS,
        name="Business",
        price_label="$499 / month",
        blurb="For engineering firms and estimating teams with sustained project volume.",
        features=[
            "2,000 AI credits monthly",
            "Entity bid-item templates",
            "Project Management workspace",
            "90-day credit rollover",
        ],
        cta="Choose Business",
    ),
    PlanInfo(
        id=SubscriptionPlan.ENTERPRISE,
        name="Enterprise",
        price_label="Custom",
        blurb="For organizations needing 10,000+ AI credits, onboarding, and procurement support.",
        features=[
            "10,000+ AI credits",
            "Project Management workspace",
            "Multi-user deployment",
            "Volume and annual options",
        ],
        cta="Contact Sales",
    ),
]
