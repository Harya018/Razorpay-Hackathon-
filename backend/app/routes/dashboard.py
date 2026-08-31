"""Read-only aggregation endpoints for the merchant dashboard (Phase 6).

Everything here reads from the SAME audit_log/orders tables every other
phase already writes to and verifies — this is a new VIEW onto existing,
already-hash-chain-verified data, not a new logging system. Nothing in
this file writes to the database.
"""

import asyncio
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import requests
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import audit, gate_client
from app.config import settings
from app.database import SessionLocal, get_db
from app.models.audit_log import AuditLog
from app.models.order import Order
from app.models.product import Product

router = APIRouter(prefix="/dashboard")

# Bounded scan window for feed aggregation — hackathon scale, not indexed
# by session_id (see audit.py's own note on the same tradeoff).
_SCAN_WINDOW = 3000

HUMAN_NEGOTIATION_EVENT_TYPES = {
    "cart_assessed",
    "offer_decision",
    "gate_call",
    "gate_decision",
    "offer_proposed",
    "response_interpreted",
    "negotiation_closed",
    "offer_generation_failed",
    "customer_mindset_summary",  # Phase 10, Part B
}
AGENT_EVENT_TYPES = {
    "agent_negotiate_requested",
    "agent_negotiate_decided",
    "agent_purchase_402",
    "agent_payment_completed",
}


def _load_recent_payloads(db: Session) -> list[dict]:
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(_SCAN_WINDOW).all()
    out = []
    for row in rows:
        try:
            payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        out.append({"id": row.id, "event_type": row.event_type, "payload": payload, "created_at": row.created_at, "order_id": row.order_id})
    return out


def _classify_channel(event_type: str, payload: dict) -> str:
    if payload.get("buyer_agent_id"):
        return "agent"
    session_id = payload.get("session_id")
    if session_id and str(session_id).startswith("agent-negotiate-"):
        return "agent"
    if event_type in HUMAN_NEGOTIATION_EVENT_TYPES:
        return "human"
    if event_type in ("order_created", "checkout_token_rejected"):
        return payload.get("channel") or "human"
    return "other"


def money(paise: Optional[int]) -> Optional[float]:
    return round(paise / 100, 2) if paise is not None else None


# ---------------------------------------------------------------------------
# GET /dashboard/summary
# ---------------------------------------------------------------------------


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    orders = db.query(Order).all()
    products = {p.id: p for p in db.query(Product).all()}

    order_created_by_order_id: dict[int, dict] = {}
    for row in db.query(AuditLog).filter(AuditLog.event_type == "order_created").all():
        try:
            payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            continue
        if row.order_id is not None:
            order_created_by_order_id[row.order_id] = payload

    # Phase 18.6 fix — this used to be "not failed" (i.e. `created` OR
    # `paid`), which meant an order that was simply never completed
    # (refresh mid-checkout, closed the payment tab, abandoned) counted
    # as real revenue even though no payment was EVER made — reproduced
    # live: creating an order and never paying it inflated total_revenue
    # by the full product price. Only `paid` orders represent money
    # actually collected; `total_orders`/`orders_by_status` below still
    # show every attempt, including abandoned ones, since that's a
    # legitimate funnel view — just never counted as revenue.
    paid_orders = [o for o in orders if o.status == "paid"]
    by_status = Counter(o.status for o in orders)

    human_orders = [o for o in paid_orders if o.channel == "human"]
    agent_orders = [o for o in paid_orders if o.channel == "agent"]

    recovered_total_paise = 0
    discounted_order_count = 0
    for o in paid_orders:
        payload = order_created_by_order_id.get(o.id)
        if not payload or not payload.get("discount_applied"):
            continue
        product = products.get(payload.get("product_id"))
        quantity = payload.get("quantity") or 1
        if not product:
            continue
        list_price = product.price * quantity
        recovered = list_price - o.amount
        if recovered > 0:
            recovered_total_paise += recovered
            discounted_order_count += 1

    return {
        "total_orders": len(orders),
        "total_revenue": money(sum(o.amount for o in paid_orders)),
        "orders_by_status": dict(by_status),
        "channel_breakdown": {
            "human": {"orders": len(human_orders), "revenue": money(sum(o.amount for o in human_orders))},
            "agent": {"orders": len(agent_orders), "revenue": money(sum(o.amount for o in agent_orders))},
        },
        "revenue_recovered_via_negotiation": money(recovered_total_paise),
        "discounted_order_count": discounted_order_count,
    }


# ---------------------------------------------------------------------------
# GET /dashboard/negotiations — human channel
# ---------------------------------------------------------------------------


def _human_headline(product_name, offer, gate_decision, final_status, closed) -> str:
    product = product_name or "a product"
    if closed:
        if final_status == "accepted":
            value = offer.get("value") if offer else None
            price = f"₹{value / 100:.2f}" if value is not None else "the negotiated price"
            return f"Accepted offer on {product} at {price}"
        if final_status == "rejected":
            return f"Shopper declined the offer on {product}"
        return f"Negotiation on {product} ended ({final_status or 'no offer made'})"
    if gate_decision is not None:
        if gate_decision.get("approved"):
            return f"Gate approved an offer on {product} — awaiting shopper's reply"
        return f"Gate rejected a proposal on {product} ({gate_decision.get('reason')})"
    if offer:
        return f"Proposed an offer on {product}"
    return f"Assessing cart for {product}"


def _summarize_human_session(session_id: str, events: list[dict]) -> dict:
    product_name = None
    offer = None
    gate_decision = None
    final_status = None
    closed = False
    mindset_summary = None  # Phase 10, Part B — AI-generated, best-effort; None if it wasn't produced

    for e in events:
        p = e["payload"]
        et = e["event_type"]
        if et == "cart_assessed":
            product_name = p.get("product_name")
        elif et == "offer_proposed":
            offer = {"type": p.get("type"), "value": p.get("value")}
        elif et == "gate_decision":
            gate_decision = {"approved": p.get("approved"), "reason": p.get("reason"), "max_allowed": p.get("max_allowed")}
        elif et == "negotiation_closed":
            final_status = p.get("final_status")
            closed = True
        elif et == "customer_mindset_summary":
            mindset_summary = p.get("summary")

    last = events[-1]
    return {
        "session_id": session_id,
        "product_name": product_name,
        "proposed_offer": offer,
        "gate_decision": gate_decision,
        "final_status": final_status,
        "closed": closed,
        "mindset_summary": mindset_summary,
        "headline": _human_headline(product_name, offer, gate_decision, final_status, closed),
        "event_count": len(events),
        "last_updated": last["created_at"].isoformat(),
        "events": [
            {"event_type": e["event_type"], "payload": e["payload"], "created_at": e["created_at"].isoformat()} for e in events
        ],
    }


@router.get("/negotiations")
def dashboard_negotiations(db: Session = Depends(get_db), limit: int = 20):
    rows = _load_recent_payloads(db)

    sessions: dict[str, list[dict]] = {}
    for row in rows:
        payload = row["payload"]
        sid = payload.get("session_id")
        if not sid or sid.startswith("agent-negotiate-"):
            continue
        if row["event_type"] not in HUMAN_NEGOTIATION_EVENT_TYPES:
            continue
        sessions.setdefault(sid, []).append(row)

    summaries = []
    for sid, events in sessions.items():
        events.sort(key=lambda e: e["id"])
        summaries.append(_summarize_human_session(sid, events))

    summaries.sort(key=lambda s: s["last_updated"], reverse=True)
    return summaries[:limit]


# ---------------------------------------------------------------------------
# GET /dashboard/agent-activity — agent-to-agent channel
# ---------------------------------------------------------------------------


def _agent_headline(buyer_agent_id, decision, purchase_402, payment, token_rejected) -> str:
    if payment is not None:
        amount = payment.get("amount")
        price = f"₹{amount / 100:.2f}" if amount is not None else "an unknown price"
        return f"{buyer_agent_id} completed purchase at {price}"
    if token_rejected is not None:
        return f"{buyer_agent_id} presented an invalid/expired token — charged full price"
    if purchase_402 is not None:
        amount = purchase_402.get("quoted_amount")
        price = f"₹{amount / 100:.2f}" if amount is not None else "an unknown price"
        return f"{buyer_agent_id} requested purchase — quoted {price} (402, awaiting payment)"
    if decision is not None:
        if decision.get("approved"):
            value = (decision.get("final_terms") or {}).get("value")
            price = f"₹{value / 100:.2f}" if value is not None else "approved terms"
            return f"{buyer_agent_id} negotiated — gate approved {price}"
        return f"{buyer_agent_id} negotiated — gate rejected ({decision.get('reason')})"
    return f"{buyer_agent_id} activity"


def _summarize_agent_group(group_key: str, events: list[dict], products_by_id: dict[int, str]) -> dict:
    buyer_agent_id = None
    kind = "other"
    proposed_terms = None
    decision = None
    purchase_402 = None
    payment = None
    token_rejected = None
    product_id = None  # Merchant Dashboard revamp: resolved to a name below

    for e in events:
        p = e["payload"]
        et = e["event_type"]
        buyer_agent_id = buyer_agent_id or p.get("buyer_agent_id")
        product_id = product_id or p.get("product_id")
        if et == "agent_negotiate_requested":
            kind = "negotiate"
            proposed_terms = p.get("proposed_terms") or p.get("requested_offer")
        elif et == "agent_negotiate_decided":
            kind = "negotiate"
            decision = {
                "approved": p.get("approved"),
                "reason": p.get("reason"),
                "max_allowed": p.get("max_allowed"),
                "final_terms": p.get("final_terms"),
            }
        elif et == "agent_purchase_402":
            kind = "purchase"
            purchase_402 = {"quoted_amount": p.get("quoted_amount"), "product_id": p.get("product_id"), "quantity": p.get("quantity")}
        elif et == "agent_payment_completed":
            kind = "purchase"
            payment = {"amount": p.get("amount")}
        elif et == "checkout_token_rejected":
            kind = "purchase"
            token_rejected = {"reason": p.get("reason")}

    last = events[-1]
    return {
        "group_key": group_key,
        "buyer_agent_id": buyer_agent_id,
        "product_name": products_by_id.get(product_id) if product_id is not None else None,
        "kind": kind,
        "proposed_terms": proposed_terms,
        "gate_decision": decision,
        "purchase_quote": purchase_402,
        "payment": payment,
        "token_rejected": token_rejected,
        "headline": _agent_headline(buyer_agent_id, decision, purchase_402, payment, token_rejected),
        "event_count": len(events),
        "last_updated": last["created_at"].isoformat(),
        "events": [
            {"event_type": e["event_type"], "payload": e["payload"], "created_at": e["created_at"].isoformat()} for e in events
        ],
    }


@router.get("/agent-activity")
def dashboard_agent_activity(db: Session = Depends(get_db), limit: int = 20):
    rows = _load_recent_payloads(db)
    products_by_id = {p.id: p.name for p in db.query(Product).all()}

    relevant_event_types = AGENT_EVENT_TYPES | {"checkout_token_rejected"}
    groups: dict[str, list[dict]] = {}
    for row in rows:
        payload = row["payload"]
        buyer_agent_id = payload.get("buyer_agent_id")
        if not buyer_agent_id or row["event_type"] not in relevant_event_types:
            continue
        group_key = payload.get("session_id") or payload.get("terms_reference") or f"{buyer_agent_id}:{row['id']}"
        groups.setdefault(group_key, []).append(row)

    summaries = []
    for group_key, events in groups.items():
        events.sort(key=lambda e: e["id"])
        summaries.append(_summarize_agent_group(group_key, events, products_by_id))

    summaries.sort(key=lambda s: s["last_updated"], reverse=True)
    return summaries[:limit]


# ---------------------------------------------------------------------------
# GET /dashboard/stream — SSE, tagged by channel
# ---------------------------------------------------------------------------


@router.get("/stream")
async def dashboard_stream(request: Request):
    async def event_generator():
        db = SessionLocal()
        try:
            latest = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
            last_id = latest.id if latest else 0
        finally:
            db.close()

        while True:
            if await request.is_disconnected():
                break

            db = SessionLocal()
            try:
                new_rows = db.query(AuditLog).filter(AuditLog.id > last_id).order_by(AuditLog.id.asc()).all()
                for row in new_rows:
                    try:
                        payload = json.loads(row.payload) if row.payload else {}
                    except (TypeError, json.JSONDecodeError):
                        payload = {}
                    channel = _classify_channel(row.event_type, payload)
                    data = {
                        "id": row.id,
                        "event_type": row.event_type,
                        "payload": payload,
                        "created_at": row.created_at.isoformat(),
                        "channel": channel,
                    }
                    yield f"data: {json.dumps(data)}\n\n"
                    last_id = row.id
            finally:
                db.close()

            await asyncio.sleep(1.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# GET /dashboard/security-posture — Phase 11f
# ---------------------------------------------------------------------------

# Filenames redteam/report.py's write_results() writes — duplicated here
# rather than imported (redteam/ is a separate project, own venv, no code
# coupling — this backend only ever reads the JSON files it produces, the
# same "read the public artifact, don't import the implementation" rule
# this whole project applies to its own sibling-service boundaries).
_SECURITY_CATEGORY_FILES = {
    "concurrency": "concurrency_results.json",
    "replay": "replay_results.json",
    "injection": "injection_results.json",
    "tampering": "tampering_results.json",
    "trust_boundary": "trust_results.json",
}


@router.get("/security-posture")
def dashboard_security_posture():
    """Reads redteam/'s own results/*.json files (concurrency, replay,
    injection, tampering, trust — one file per attack category) and
    aggregates them into a scorecard. This backend NEVER runs, imports,
    or triggers the red-team suite — it only reads whatever the suite
    last wrote to disk. If the suite has never been run (or was run
    against a different checkout), this returns an honestly-empty
    scorecard, never a fake one. total_findings counts every FAIL
    verdict honestly — a real race condition or replay gap surfaced by
    the suite counts as a finding here, never silently absorbed into the
    "blocked" total.
    """
    # Relative to backend's own CWD at process start (uvicorn is run from
    # backend/), same resolution rule DATABASE_URL's sqlite:///./app.db
    # already relies on.
    results_dir = Path(settings.RED_TEAM_RESULTS_DIR).resolve()

    all_attacks: list[dict] = []
    latest_timestamp: Optional[str] = None
    for category, filename in _SECURITY_CATEGORY_FILES.items():
        file_path = results_dir / filename
        if not file_path.exists():
            continue
        try:
            entries = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for entry in entries:
            entry["category"] = category
            all_attacks.append(entry)
            ts = entry.get("timestamp")
            if ts and (latest_timestamp is None or ts > latest_timestamp):
                latest_timestamp = ts

    total = len(all_attacks)
    blocked = sum(1 for a in all_attacks if a.get("verdict") in ("PASS", "PASS_CONFIRMS_DOCUMENTED_LIMITATION"))
    findings = [a for a in all_attacks if a.get("verdict") == "FAIL"]

    by_category: dict[str, dict] = {}
    for category in _SECURITY_CATEGORY_FILES:
        cat_attacks = [a for a in all_attacks if a["category"] == category]
        cat_total = len(cat_attacks)
        cat_blocked = sum(1 for a in cat_attacks if a.get("verdict") in ("PASS", "PASS_CONFIRMS_DOCUMENTED_LIMITATION"))
        by_category[category] = {
            "total": cat_total,
            "blocked": cat_blocked,
            "pass_rate": round(cat_blocked / cat_total, 3) if cat_total else None,
        }

    return {
        "source": "internal red-team suite (redteam/), run manually — not a third-party audit",
        "run_on": latest_timestamp,
        "total_attacks": total,
        "total_blocked": blocked,
        "total_findings": len(findings),
        "by_category": by_category,
        "attacks": sorted(all_attacks, key=lambda a: (a.get("verdict") != "FAIL", a.get("attack_id", ""))),
    }


# ---------------------------------------------------------------------------
# GET /dashboard/recovery-simulation — Phase 13
# ---------------------------------------------------------------------------


@router.get("/recovery-simulation")
def dashboard_recovery_simulation():
    """Reads metrics/recovery_sim.py's own output file and returns its
    summary block as-is. This backend NEVER runs the simulation itself —
    it only reads whatever was last written to disk. If the simulation
    has never been run, this returns an honestly-empty result, never a
    fabricated number. Every field here is clearly simulation-derived
    (see the summary's own "model_documentation" field, carried straight
    through) — this endpoint doesn't strip that caveat out.
    """
    results_path = Path(settings.RECOVERY_SIM_RESULTS_PATH).resolve()
    if not results_path.exists():
        return {"available": False, "summary": None}

    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"available": False, "summary": None}

    return {"available": True, "summary": data.get("summary")}


# ---------------------------------------------------------------------------
# GET /dashboard/audit-trail — Phase 17: the hash chain, made visible
# ---------------------------------------------------------------------------


def _serialize_chain_entries(rows: list[AuditLog]) -> list[dict]:
    out = []
    for row in rows:
        try:
            payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            payload = {}
        out.append(
            {
                "id": row.id,
                "event_type": row.event_type,
                "created_at": row.created_at.isoformat(),
                "order_id": row.order_id,
                "entry_hash": row.entry_hash,
                "entry_hash_short": (row.entry_hash or "")[:12],
                "previous_hash": row.previous_hash,
                "previous_hash_short": (row.previous_hash or "")[:12],
                "summary": payload.get("note") or payload.get("event_type") or row.event_type,
            }
        )
    return out


@router.get("/audit-trail")
def dashboard_audit_trail(db: Session = Depends(get_db), limit: int = 15):
    chain_key = audit.find_active_chain_key(db)
    if chain_key is None:
        return {"chain_key": None, "entries": [], "count": 0}
    entries = audit.get_chain_entries(db, chain_key, limit=limit)
    return {"chain_key": chain_key, "entries": _serialize_chain_entries(entries), "count": len(entries)}


@router.post("/audit-trail/verify")
def dashboard_audit_trail_verify(db: Session = Depends(get_db)):
    chain_key = audit.find_active_chain_key(db)
    if chain_key is None:
        return {"chain_key": None, "valid": None, "total_rows": 0, "broken_at_row_id": None, "reason": "no_chain_found"}
    result = audit.verify_chain(db, chain_key)
    return {
        "chain_key": chain_key,
        "valid": result.valid,
        "total_rows": result.total_rows,
        "broken_at_row_id": result.broken_at_row_id,
        "reason": result.reason,
    }


@router.get("/audit-trail/sandbox")
def dashboard_audit_trail_sandbox(db: Session = Depends(get_db)):
    entries = audit.get_chain_entries(db, audit.SANDBOX_CHAIN_KEY, limit=audit.SANDBOX_SIZE)
    if not entries:
        entries = audit.seed_sandbox_chain(db)
    return {"chain_key": audit.SANDBOX_CHAIN_KEY, "entries": _serialize_chain_entries(entries), "count": len(entries)}


@router.post("/audit-trail/sandbox/tamper")
def dashboard_audit_trail_sandbox_tamper(db: Session = Depends(get_db)):
    entries = audit.get_chain_entries(db, audit.SANDBOX_CHAIN_KEY, limit=audit.SANDBOX_SIZE)
    if not entries:
        audit.seed_sandbox_chain(db)
    audit.tamper_sandbox_chain(db)
    entries = audit.get_chain_entries(db, audit.SANDBOX_CHAIN_KEY, limit=audit.SANDBOX_SIZE)
    return {"chain_key": audit.SANDBOX_CHAIN_KEY, "entries": _serialize_chain_entries(entries), "count": len(entries)}


@router.post("/audit-trail/sandbox/verify")
def dashboard_audit_trail_sandbox_verify(db: Session = Depends(get_db)):
    result = audit.verify_chain(db, audit.SANDBOX_CHAIN_KEY)
    return {
        "chain_key": audit.SANDBOX_CHAIN_KEY,
        "valid": result.valid,
        "total_rows": result.total_rows,
        "broken_at_row_id": result.broken_at_row_id,
        "reason": result.reason,
    }


@router.post("/audit-trail/sandbox/reset")
def dashboard_audit_trail_sandbox_reset(db: Session = Depends(get_db)):
    entries = audit.seed_sandbox_chain(db)
    return {"chain_key": audit.SANDBOX_CHAIN_KEY, "entries": _serialize_chain_entries(entries), "count": len(entries)}


# ---------------------------------------------------------------------------
# GET /dashboard/policy-gate-status — Phase 17: live health of the
# separately-deployed policy-gate service, not the main backend
# ---------------------------------------------------------------------------


@router.get("/policy-gate-status")
def dashboard_policy_gate_status():
    """A LIVE ping, timed right now — not a cached/last-known value — so
    this genuinely flips to unreachable within one poll interval of the
    gate actually going down (see gate_client's own fail-CLOSED comment;
    this endpoint follows the same "never assume reachable" rule). The
    approve/deny/latency counters come from gate_client's real call
    history (every actual /evaluate + /verify this backend has made).
    """
    call_stats = gate_client.get_gate_call_stats()

    start = time.monotonic()
    try:
        resp = requests.get(f"{settings.POLICY_GATE_URL}/health", timeout=3)
        resp.raise_for_status()
        live_latency_ms = round((time.monotonic() - start) * 1000, 1)
        body = resp.json()
        return {
            "reachable": True,
            "checked_at": time.time(),
            "live_ping_latency_ms": live_latency_ms,
            "gate_uptime_seconds": body.get("uptime_seconds"),
            "backend_process_uptime_seconds": call_stats["process_uptime_seconds"],
            "total_calls": call_stats["total_calls"],
            "approved": call_stats["approved"],
            "denied": call_stats["denied"],
            "unreachable_calls": call_stats["unreachable"],
            "avg_latency_ms": call_stats["avg_latency_ms"],
        }
    except requests.RequestException:
        return {
            "reachable": False,
            "checked_at": time.time(),
            "live_ping_latency_ms": round((time.monotonic() - start) * 1000, 1),
            "gate_uptime_seconds": None,
            "backend_process_uptime_seconds": call_stats["process_uptime_seconds"],
            "total_calls": call_stats["total_calls"],
            "approved": call_stats["approved"],
            "denied": call_stats["denied"],
            "unreachable_calls": call_stats["unreachable"],
            "avg_latency_ms": call_stats["avg_latency_ms"],
        }


# ---------------------------------------------------------------------------
# GET /dashboard/agent-activity-map — Phase 17: baseline snapshot for the
# live mini architecture diagram; the frontend increments these live from
# the existing /dashboard/stream SSE feed rather than polling this again.
# ---------------------------------------------------------------------------


@router.get("/agent-activity-map")
def dashboard_agent_activity_map(db: Session = Depends(get_db)):
    seller_to_gate = db.query(AuditLog).filter(AuditLog.event_type == "gate_decision").count()
    buyer_to_gate = db.query(AuditLog).filter(AuditLog.event_type == "agent_negotiate_decided").count()
    return {
        "seller_agent_to_policy_gate": seller_to_gate,
        "buyer_agent_to_policy_gate": buyer_to_gate,
        "as_of": time.time(),
    }


# ---------------------------------------------------------------------------
# GET /dashboard/analytics — Phase 17: Sales Analytics page data. Reads
# the FULL audit_log/orders history (not the bounded _SCAN_WINDOW the
# live feeds above use) since correctness of real trend numbers matters
# more here than it does for a "recent activity" feed, and this table is
# nowhere near large enough yet for a full scan to matter.
# ---------------------------------------------------------------------------


def _bucket_label(dt, granularity: str) -> str:
    return dt.date().isoformat() if granularity == "day" else dt.strftime("%Y-%m-%d %H:00")


@router.get("/analytics")
def dashboard_analytics(db: Session = Depends(get_db)):
    orders = [o for o in db.query(Order).all() if o.status != "failed"]
    products = {p.id: p for p in db.query(Product).all()}

    span_hours = 0.0
    if orders:
        times = [o.created_at for o in orders]
        span_hours = (max(times) - min(times)).total_seconds() / 3600
    granularity = "hour" if span_hours <= 48 else "day"

    # --- revenue over time (overall + human/agent split) --------------------
    revenue_by_bucket: dict[str, int] = defaultdict(int)
    channel_revenue_by_bucket: dict[str, dict[str, int]] = defaultdict(lambda: {"human": 0, "agent": 0})
    for o in orders:
        label = _bucket_label(o.created_at, granularity)
        revenue_by_bucket[label] += o.amount
        channel_revenue_by_bucket[label][o.channel if o.channel in ("human", "agent") else "human"] += o.amount

    revenue_over_time = [
        {"bucket": label, "revenue": money(amount)} for label, amount in sorted(revenue_by_bucket.items())
    ]
    channel_revenue_over_time = [
        {"bucket": label, "human_revenue": money(v["human"]), "agent_revenue": money(v["agent"])}
        for label, v in sorted(channel_revenue_by_bucket.items())
    ]

    # --- top products by revenue --------------------------------------------
    revenue_by_product: dict[int, int] = defaultdict(int)
    orders_by_product: dict[int, int] = defaultdict(int)
    for o in orders:
        revenue_by_product[o.product_id] += o.amount
        orders_by_product[o.product_id] += 1
    top_products_by_revenue = sorted(
        (
            {"product_id": pid, "name": products[pid].name if pid in products else f"product {pid}", "revenue": money(amt), "orders": orders_by_product[pid]}
            for pid, amt in revenue_by_product.items()
        ),
        key=lambda r: r["revenue"] or 0,
        reverse=True,
    )[:10]

    # --- human-negotiation-derived: funnel, discount tiers, top-by-frequency
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    sessions: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        try:
            payload = json.loads(row.payload) if row.payload else {}
        except (TypeError, json.JSONDecodeError):
            continue
        sid = payload.get("session_id")
        if not sid or sid.startswith("agent-negotiate-") or sid.startswith("demo:"):
            continue
        if row.event_type not in HUMAN_NEGOTIATION_EVENT_TYPES:
            continue
        sessions[sid].append({"event_type": row.event_type, "payload": payload})

    started = len(sessions)
    offers_extended = 0
    accepted = 0
    rejected = 0
    tier_counts: dict[str, int] = defaultdict(int)
    negotiation_count_by_product: dict[str, int] = defaultdict(int)

    TIER_LABELS = {1: "5% (attempt 1)", 2: "10% (attempt 2)"}

    for sid, events in sessions.items():
        product_name = None
        offers = []
        final_status = None
        for e in events:
            p = e["payload"]
            if e["event_type"] == "cart_assessed":
                # Prefer the CURRENT product name (live join) over the
                # payload's own snapshot — so a since-renamed product (e.g.
                # the Phase 17 catalog rewrite) reads consistently with
                # "Top products by revenue" above, which is always current.
                # Falls back to the snapshot if the product was deleted.
                live_product = products.get(p.get("product_id"))
                product_name = live_product.name if live_product else p.get("product_name")
            elif e["event_type"] == "offer_proposed":
                offers.append(p)
            elif e["event_type"] == "negotiation_closed":
                final_status = p.get("final_status")

        if product_name:
            negotiation_count_by_product[product_name] += 1
        if offers:
            offers_extended += 1
        if final_status == "accepted":
            accepted += 1
            last_offer = offers[-1] if offers else None
            attempt = last_offer.get("attempt_number") if last_offer else None
            label = TIER_LABELS.get(attempt, f"10% final/urgency (attempt {attempt})" if attempt else "unknown")
            tier_counts[label] += 1
        elif final_status == "rejected":
            rejected += 1

    abandoned = started - accepted - rejected

    top_products_by_negotiation_frequency = sorted(
        ({"name": name, "session_count": count} for name, count in negotiation_count_by_product.items()),
        key=lambda r: r["session_count"],
        reverse=True,
    )[:10]

    return {
        "granularity": granularity,
        "revenue_over_time": revenue_over_time,
        "channel_revenue_over_time": channel_revenue_over_time,
        "top_products_by_revenue": top_products_by_revenue,
        "top_products_by_negotiation_frequency": top_products_by_negotiation_frequency,
        "negotiation_funnel": {
            "sessions_started": started,
            "offers_extended": offers_extended,
            "accepted": accepted,
            "rejected": rejected,
            "abandoned": max(abandoned, 0),
            "note": "abandoned = sessions with no recorded acceptance/rejection yet (includes any still in progress)",
        },
        "discount_tier_breakdown_real": dict(tier_counts),
        "source_note": "Computed from real audit-log negotiation and order history — NOT the simulated Revenue Recovery card.",
    }
