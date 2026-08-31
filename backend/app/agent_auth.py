import hashlib
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.buyer_agent import BuyerAgent

API_KEY_PREFIX = "bak_"  # "buyer agent key" — visually distinct from Razorpay/Groq/gate key formats


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def require_buyer_agent(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
) -> BuyerAgent:
    """FastAPI dependency for every /agent/v1/* write endpoint. Expects
    `Authorization: Bearer <api_key>`. Returns the authenticated BuyerAgent
    row — callers must still check payload.buyer_agent_id against
    buyer.buyer_agent_id, since the identity here comes from the key, not
    from anything the client claims in the request body.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    api_key = authorization[len("Bearer ") :].strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    buyer = db.query(BuyerAgent).filter(BuyerAgent.api_key_hash == hash_api_key(api_key)).first()
    if buyer is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return buyer
