import time
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import AuthUser, identity_from_claims, require_user
from app.config import settings
from app.database import get_db
from app.models.customer_profile import CustomerProfile

router = APIRouter(prefix="/auth")


# The only purpose of this endpoint: let the frontend show a coherent
# "signed in as X (SHOPPER)" / "sign in with Google" UI state without
# trying to decode the Supabase JWT itself. It does NOT grant anything —
# every actual protected route (everything under /dashboard, POST
# /product, the agent-commerce ownership checks) independently re-verifies
# the token and re-derives the role itself via require_user/
# require_merchant_admin. A tampered/forged frontend response from this
# endpoint could at worst show a misleading UI state; it can never bypass
# a real authorization check anywhere else in the system.
@router.get("/me")
def whoami(user: AuthUser = Depends(require_user), db: Session = Depends(get_db)):
    identity = identity_from_claims(user)
    profile = db.get(CustomerProfile, user.sub)
    if profile and profile.display_name:
        identity["name"] = profile.display_name
    identity["has_profile"] = profile is not None
    return identity


# Demo-only one-click sign-in — NOT a real OAuth flow, and NOT available
# unless DEMO_MODE is on. This exists because a real Google login requires
# a real Supabase project (VITE_SUPABASE_URL/ANON_KEY), which a local demo
# checkout of this project won't have configured. Rather than weakening
# require_merchant_admin to accept an unsigned/unverified token, this
# mints a REAL HS256 token signed with the backend's own
# SUPABASE_JWT_SECRET — the exact same secret require_user() verifies
# against — so the token that comes back is checked by the real
# signature-verification code path, not a bypass of it. Two personas:
# "merchant" gets the first MERCHANT_ADMIN_EMAILS address (so the real
# allowlist is what grants MERCHANT_ADMIN — same rule as a Google login);
# "shopper" gets a plain customer identity with no admin claim at all, so
# the role-boundary tests (a shopper hitting /dashboard) exercise the
# real 403 path. Only when DEMO_MODE=1 is explicitly set — this must stay
# off in any deployment with a real Supabase project.
@router.post("/demo-login")
def demo_login(role: Literal["merchant", "shopper"] = "merchant"):
    if not settings.DEMO_MODE:
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=503, detail="DEMO_MODE sign-in requires SUPABASE_JWT_SECRET to be set locally")

    if role == "merchant":
        admin_emails = [e.strip() for e in settings.MERCHANT_ADMIN_EMAILS.split(",") if e.strip()]
        email = admin_emails[0] if admin_emails else "demo-merchant@example.com"
        claims = {"sub": "demo-merchant", "email": email, "app_metadata": {"role": "MERCHANT_ADMIN", "provider": "demo"}, "user_metadata": {"full_name": "Priya (Demo Merchant)"}}
    else:
        email = "demo-shopper@example.com"
        claims = {"sub": "demo-shopper", "email": email, "app_metadata": {"provider": "demo"}, "user_metadata": {"full_name": "Demo Shopper"}}

    now = int(time.time())
    token = jwt.encode({**claims, "iat": now, "exp": now + 24 * 3600}, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
    return {"access_token": token, "email": email, "role": "MERCHANT_ADMIN" if role == "merchant" else "SHOPPER"}
