from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import AuthUser, identity_from_claims, require_user
from app.database import get_db
from app.models.customer_profile import CustomerProfile

router = APIRouter(prefix="/profile")


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20, pattern=r"^[0-9+\-\s()]*$")
    address_line: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=80)
    pincode: str | None = Field(default=None, max_length=10, pattern=r"^[0-9A-Za-z\- ]*$")


def _serialize(user: AuthUser, profile: CustomerProfile | None) -> dict:
    identity = identity_from_claims(user)
    if profile and profile.display_name:
        identity["name"] = profile.display_name
    return {
        **identity,
        "profile": {
            "display_name": profile.display_name if profile else None,
            "phone": profile.phone if profile else None,
            "address_line": profile.address_line if profile else None,
            "city": profile.city if profile else None,
            "pincode": profile.pincode if profile else None,
            "updated_at": profile.updated_at.isoformat() if profile else None,
        },
    }


# Identity always keyed on the VERIFIED token's sub — the request body
# never names a user, so one customer cannot read or write another's row.
@router.get("")
def get_profile(user: AuthUser = Depends(require_user), db: Session = Depends(get_db)):
    return _serialize(user, db.get(CustomerProfile, user.sub))


@router.put("")
def update_profile(payload: ProfileUpdate, user: AuthUser = Depends(require_user), db: Session = Depends(get_db)):
    profile = db.get(CustomerProfile, user.sub)
    if profile is None:
        profile = CustomerProfile(user_id=user.sub)
        db.add(profile)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(profile)
    return _serialize(user, profile)
