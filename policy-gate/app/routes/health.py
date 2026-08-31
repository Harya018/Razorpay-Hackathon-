import time

from fastapi import APIRouter

router = APIRouter()

# Recorded at import time (i.e. process start) — the backend's Policy
# Gate Status panel derives "uptime" from this, which is only meaningful
# if it resets whenever this process restarts (e.g. the Phase 14 "kill
# the gate" demo beat), which it does since it's a plain module global.
_STARTED_AT = time.time()


@router.get("/health")
def health():
    return {"status": "ok", "uptime_seconds": round(time.time() - _STARTED_AT, 1)}
