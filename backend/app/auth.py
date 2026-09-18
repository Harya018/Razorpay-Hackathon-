from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWKClient

from app.config import settings


@dataclass(frozen=True)
class AuthUser:
    sub: str
    email: str | None
    role: str
    claims: dict


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient | None:
    if not settings.SUPABASE_URL:
        return None
    return PyJWKClient(f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json")


def _decode_supabase_jwt(token: str) -> dict:
    options = {"verify_aud": False}
    if settings.SUPABASE_JWT_SECRET:
        return jwt.decode(token, settings.SUPABASE_JWT_SECRET, algorithms=["HS256"], options=options)

    client = _jwks_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Supabase auth is not configured")
    signing_key = client.get_signing_key_from_jwt(token)
    return jwt.decode(token, signing_key.key, algorithms=["RS256", "ES256"], options=options)


def _role_from_claims(claims: dict) -> str:
    app_metadata = claims.get("app_metadata") or {}
    user_metadata = claims.get("user_metadata") or {}
    role = app_metadata.get("role") or user_metadata.get("role") or claims.get("role") or "SHOPPER"
    email = (claims.get("email") or "").lower()
    if email and email in settings.merchant_admin_emails:
        return "MERCHANT_ADMIN"
    return str(role).upper()


def require_user(request: Request, authorization: str = Header(default=None)) -> AuthUser:
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
    elif request.query_params.get("access_token"):
        token = request.query_params["access_token"].strip()
    else:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        claims = _decode_supabase_jwt(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid authentication token") from exc
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    return AuthUser(sub=sub, email=claims.get("email"), role=_role_from_claims(claims), claims=claims)

def require_merchant_admin(user: AuthUser = Depends(require_user)) -> AuthUser:
    if user.role != "MERCHANT_ADMIN":
        raise HTTPException(status_code=403, detail="MERCHANT_ADMIN role required")
    return user


def optional_user(request: Request, authorization: str = Header(default=None)) -> AuthUser | None:
    """For routes that work for guests but ATTRIBUTE to a signed-in user when
    one is present (checkout). A present-but-invalid token is still an
    error — never silently downgraded to guest, so a forged token can't be
    used to strip attribution either.
    """
    if not authorization and not request.query_params.get("access_token"):
        return None
    return require_user(request, authorization)


def identity_from_claims(user: AuthUser) -> dict:
    """The safe, display-only identity fields a Supabase token carries —
    what /auth/me and the profile pages show. Nothing here is trusted for
    authorization (that's `role`, re-derived server-side); it's purely
    "who does the token say you are."
    """
    c = user.claims
    um = c.get("user_metadata") or {}
    am = c.get("app_metadata") or {}
    return {
        "sub": user.sub,
        "email": user.email,
        "role": user.role,
        "name": um.get("full_name") or um.get("name") or None,
        "avatar_url": um.get("avatar_url") or um.get("picture") or None,
        "provider": am.get("provider") or ("demo" if user.sub.startswith("demo-") else None),
        # Supabase access tokens carry iat (issued-at) but not the account's
        # creation date — that lives in Supabase's user table, which this
        # backend never queries. Reported honestly as the session's issue time.
        "session_issued_at": c.get("iat"),
        "session_expires_at": c.get("exp"),
    }
