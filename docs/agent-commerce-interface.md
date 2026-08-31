# Agent Commerce Interface — v1

**Status:** Frozen (Phase 4a). This document is the contract. If you are
building a buyer-agent client, everything you need is here — you should
never need to read this store's backend source code.

**Base URL (local dev):** `http://localhost:8010`
**Prefix:** all endpoints below are under `/agent/v1/`.

## What this is, and what it isn't

This is a small, honest HTTP interface that lets a non-human buyer browse
a catalog, optionally negotiate a discount, and complete a purchase
against a real Razorpay test-mode payment.

It is **shaped like** the emerging x402 pattern (an unauthorized purchase
attempt gets met with a structured `402 Payment Required` response
describing what would satisfy it, rather than a bare error) and it
**reuses the same enforcement machinery** — the policy-gate and the order
pipeline — that the human negotiation channel uses. Nothing here is a
separate, weaker path.

**What it explicitly does NOT claim:**
- As of Phase 8, `/purchase` and `/pay` speak x402 V2's actual **wire
  format** (header names, base64-JSON encoding, object shapes) — see
  "x402 V2 Conformance and Its Limits" below before assuming anything
  about what that does and doesn't mean. It is still **not** a
  conformant implementation of ACP (Agentic Commerce Protocol) or AP2,
  and it is not a conformant implementation of x402's *settlement*
  layer — only its transport/header shape. A client built strictly
  against real x402 expecting on-chain settlement will not work here
  out of the box; a client built against this document's header shapes
  will.
- There is no automated, in-band payment-proof mechanism. `/purchase`
  never succeeds directly — it always returns `402` with terms, and
  completing payment is a **separate, explicit** call to `/pay`. There is
  no support for a buyer agent to supply its own cryptographic payment
  proof; `/pay` creates a real Razorpay order the same way the human
  checkout flow does.
- Every `BuyerAgent` has a `spending_ceiling` column (paise, per order),
  but **`POST /agent/v1/register` does not accept one** — a buyer agent
  cannot declare its own spending limit, by design. It is always `null`
  for every identity registered in this phase, and no endpoint currently
  enforces it even when set. Treat it as reserved for a future phase
  (assigned out-of-band by the merchant), not a live control.
- `GET /agent/v1/order/{order_id}/status` has no authentication or
  ownership check — any caller who knows an order_id can read its status.
  This matches the existing (also-unauthenticated) human order flow; it
  is not a new gap introduced here.
- Every product in the catalog is currently marked `negotiable: true`.
  There is no mechanism yet for a merchant to mark a specific SKU as
  fixed-price-only.

## Standard error shape

Every error response this interface's own logic raises (`401`, `403`,
`404`, `409`, `400`, `402`'s non-error usage aside) is a JSON object with
a single `detail` **string**:

```json
{"detail": "Product not found"}
```

The one exception is `422 Unprocessable Entity` — a request body that
fails basic type/shape validation before any endpoint logic runs (e.g.
`quantity: 0`, a missing required field). That's raised by the underlying
framework, not this interface's own logic, and `detail` there is an
**array** of validation error objects, not a string:

```json
{"detail": [{"type": "greater_than", "loc": ["body", "quantity"], "msg": "Input should be greater than 0", "input": 0, "ctx": {"gt": 0}}]}
```

Check whether `detail` is a string or an array if you need to branch on
error type programmatically.

## Authentication

Every **write** endpoint (`/negotiate`, `/purchase`, `/pay`) requires an
`Authorization: Bearer <api_key>` header, where `<api_key>` was issued by
`POST /agent/v1/register`. Read endpoints (`/catalog`, `/product/{id}`,
`/order/{order_id}/status`) require no authentication.

The identity that matters is the one resolved from the API key — every
authenticated request body also carries a `buyer_agent_id` field, and the
server rejects the request (`403`) if it doesn't match the key's own
identity. Don't rely on the body field alone; it exists so the payload is
self-describing, not as the actual authorization mechanism.

### `POST /agent/v1/register`

Registers a new buyer agent identity and issues an API key. **The key is
shown exactly once, in this response.** It is never stored in plaintext
and cannot be recovered later — if it's lost, register a new identity.

Request:
```json
{
  "buyer_agent_id": "acme-shopping-bot",
  "display_name": "Acme Shopping Bot"
}
```

`display_name` is optional, stored as given, and otherwise unused by any
endpoint — it exists purely for a human to later recognize which agent is
which. `buyer_agent_id` must be unique — registering an already-taken id
returns `409`.

Response (`201`):
```json
{
  "buyer_agent_id": "acme-shopping-bot",
  "api_key": "bak_9k2f...redacted...",
  "created_at": "2026-08-24T10:00:00.000000"
}
```

Errors: `409` — `{"detail": "buyer_agent_id already registered"}`

---

## Catalog

### `GET /agent/v1/catalog`

No authentication required.

Response (`200`):
```json
[
  {
    "id": 1,
    "name": "Wireless Headphones",
    "description": "Noise-cancelling, test SKU",
    "price": 249900,
    "currency": "INR",
    "stock": 15,
    "negotiable": true
  }
]
```

`price` is an integer in **paise** (smallest currency unit) — never a
float, never rupees. `1 rupee = 100 paise`. `description` is `null` for
products that were created without one — don't assume it's always present.

**Revision note (added post-freeze):** `description` was added to this
response after the initial freeze — it was missing from v1.0.0 despite
being necessary for any client trying to match a natural-language goal
against the catalog using more than just a product name. This is exactly
the kind of gap the frozen-doc process exists to catch: found while
building an independent client against the original doc, fixed here
rather than worked around by reading the backend source. No other field
changed; existing clients built against the name-only version are
unaffected (this is a strictly additive change).

### `GET /agent/v1/product/{id}`

Same object shape as one catalog entry. `404` if the id doesn't exist.

---

## Negotiation

### `POST /agent/v1/negotiate`

**Requires authentication.** Proposes terms for a product and gets an
immediate, deterministic decision from the merchant's policy gate — the
same gate the human negotiation channel calls, with the same rules. This
is a single-shot evaluation, not a multi-turn conversation: each call is
independent (there is no server-side memory of prior calls on this
endpoint the way the human chat negotiation has turns).

Request:
```json
{
  "product_id": 1,
  "quantity": 1,
  "buyer_agent_id": "acme-shopping-bot",
  "proposed_terms": {
    "type": "discount",
    "value": 224910
  }
}
```

`proposed_terms.type` is `"discount"` or `"bundle"`. `proposed_terms.value`
is the proposed **final total price for the whole cart**, in paise — not
a percentage, not a per-unit price.

Response when approved (`200`):
```json
{
  "approved": true,
  "approval_token": "5be3ae9c...64 hex chars...",
  "final_terms": {"type": "discount", "value": 224910},
  "reason": null,
  "max_allowed": null
}
```

Response when rejected (`200` — rejection is a normal, successful
response, not an HTTP error):
```json
{
  "approved": false,
  "approval_token": null,
  "final_terms": null,
  "reason": "below_floor_or_exceeds_max_discount",
  "max_allowed": 224910
}
```

`max_allowed`, when present, is the total price (paise) the merchant
*would* accept — a buyer agent can immediately retry `/negotiate` with
that exact value if it wants the best available deal. `reason` values
currently used by the gate: `below_floor_or_exceeds_max_discount`,
`bundle_effective_price_below_floor`, `bundle_has_no_priced_terms_to_evaluate`,
`discount_value_exceeds_original_price`, `missing_discount_value`,
`no_offer_to_evaluate`, `attempt_cap_exceeded`, `unknown_offer_type`,
`gate_unreachable: <detail>`. Treat this as an open set — don't
hard-code an exhaustive match against it.

`approval_token`, when present, is single-use and tied to this exact
`product_id` + `quantity` + `final_terms.value`. It's consumed the first
time `/pay` successfully verifies it — reusing it, or presenting it for a
different quantity, fails.

**Known limitation — token freshness:** a token does **not** expire on
its own, and re-negotiating does not invalidate a previous, unused token
from the same session. If a client negotiates, waits, negotiates again,
and then purchases, an earlier token is still technically valid and
redeemable even though it no longer reflects the client's most recent
ask. This interface has no fix for that in Phase 4a/4b — the correct
integration pattern is for a client to always call `/negotiate`
immediately before `/purchase` → `/pay` in the same flow, never caching
or reusing a token across separate negotiation attempts.

Errors: `401` (bad/missing key), `403` (`buyer_agent_id` doesn't match
the authenticated key), `404` (product not found).

---

## x402 V2 Conformance and Its Limits

**Read this before assuming anything about the payment headers described
below, and before repeating any "x402" claim about this project anywhere
else (a pitch, a README, a support ticket).** Omitting this section turns
an honest claim into a false one.

**Phase 11 update:** the `scheme`/`network` VALUES below are Phase 8's
originals and are now stale — Phase 11 renamed them (`scheme` is now
`"exact"`, `network` is now `"inr-fiat:razorpay-test"`), made
`PAYMENT-SIGNATURE` required on `/pay` rather than optional, and added a
`GET /agent/v1/discovery` endpoint. **`docs/x402-v2-conformance.md` is
the current, authoritative reference for the exact wire shapes** — this
section stays as the original honesty-boundary argument (still fully
correct in spirit) and historical record of Phase 8's first pass.

As of Phase 8, `/agent/v1/purchase` and `/agent/v1/pay` additionally speak
x402 V2's actual **wire format** — the header names, base64-JSON
encoding, and `PaymentRequired` / `PaymentPayload` / `SettlementResponse`
object shapes defined in the
[x402 V2 specification](https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md)
and its [HTTP transport](https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md).
This is a real, checkable upgrade from Phase 4a's "shaped like x402"
language — but it is a **transport-format** conformance claim only, never
a settlement-protocol one. Those are two different claims; only the first
is true here.

**What actually changed:** the header names (`PAYMENT-REQUIRED`,
`PAYMENT-SIGNATURE`, `PAYMENT-RESPONSE`), the base64 encoding, and the
field names inside each object (`scheme`, `network`, `amount`, `asset`,
`payTo`, `maxTimeoutSeconds`, `extra`, `x402Version`, `accepted`,
`payload`, `success`, `errorReason`, `transaction`, `payer`, etc.) now
match the real spec. A client written against x402 V2's header contract
can parse these headers without knowing anything about this merchant.

**What did NOT change, and cannot, without lying:** real x402 settles
payment **on-chain** — a client signs an EIP-3009 authorization for a
stablecoin transfer (USDC on Base or Solana), a facilitator submits and
verifies it, and `SettlementResponse.transaction` is a real blockchain
transaction hash. This merchant settles in **INR via Razorpay, test
mode** — there is no blockchain, no facilitator, no signed authorization,
and no transaction hash anywhere in this codebase. Concretely, here is
every field where the *shape* is real x402 but the *meaning* had to be
substituted for a fiat merchant:

| Field | Real x402 meaning | What it holds in this system |
|---|---|---|
| `scheme` | Identifies a settlement method, e.g. `"exact"` (EIP-3009 exact-amount transfer) | `"razorpay-inr"` — a scheme name that doesn't exist in the real spec's registry, deliberately, so it's never mistaken for a spec-registered one |
| `network` | CAIP-2 chain id, e.g. `"eip155:8453"` (Base) | `"razorpay-test-inr"` — a plain label, not a chain id |
| `asset` | An ERC-20 token contract address (the spec also allows an ISO 4217 code as a fallback) | `"INR"` — using the spec's own ISO 4217 allowance, so this one field is a genuinely direct fit |
| `amount` | Atomic token units (e.g. USDC's 6 decimals) as a string | Paise — INR's own atomic unit (1 rupee = 100 paise) — as a string. Also a natural fit |
| `payTo` | The merchant's on-chain wallet address | This merchant's Razorpay **public** key id (`RAZORPAY_KEY_ID`) — not a secret, already exposed client-side for the Razorpay checkout widget elsewhere in this project, but not a payment address in any on-chain sense |
| `maxTimeoutSeconds` | An enforced deadline for the client to submit payment | Present for shape conformance (`300`) but **not enforced** — this project's known token-freshness limitation (documented above, under Negotiation) was an explicit Phase 4b decision not to add expiry logic; that decision still stands |
| `payload.signature` / `payload.authorization` (the "exact" EVM scheme's fields) | A cryptographic signature over an EIP-3009 authorization | Replaced entirely with `{terms_reference, approval_token}` — this system's actual proof of authorization. `terms_reference` is what `/purchase` minted; `approval_token` is the policy-gate's own single-use, buyer-bound approval. See "Negotiation" and "Purchase" below for what these really are |
| `transaction` (in `SettlementResponse`) | A blockchain transaction hash | The Razorpay `razorpay_order_id` on success, or an empty string `""` on failure. **This is not a transaction hash and not proof of on-chain settlement — it is a Razorpay test-mode order id, and nothing more.** |
| `payer` (in `SettlementResponse`) | A wallet address | The buyer's `buyer_agent_id` string |

**`PAYMENT-RESPONSE` on both outcomes:** the v2 spec explicitly calls out
a known bug class where implementations attach the settlement-response
header only on success and silently omit it on failure. This
implementation attaches `PAYMENT-RESPONSE` to both `/pay`'s success path
and its one settlement-level rejection path (an unknown or already-used
`terms_reference`). It is **not** attached to generic pre-settlement
authentication failures (`401`/`403`) — those happen before a settlement
decision is even evaluated, so they aren't a settlement outcome in the
sense this header exists to describe.

**Backward compatibility:** these headers are strictly additive. The JSON
response bodies documented below for `/purchase` and `/pay` are
unchanged — Phase 4b's buyer agent (or any client built against the pre-
Phase-8 version of this document) continues to work without reading a
single header.

**Bottom line:** point a generic x402 V2 client expecting on-chain
settlement at this merchant, and it will not work — the `transaction`
field it gets back is a Razorpay order id, and there is no facilitator to
verify anything on-chain. Point a client built specifically for this
merchant's header/JSON shapes at it, and it will — because that shape is
now real x402 V2, just riding a fiat settlement rail instead of a
blockchain one.

### Header reference

| Header | Direction | Carries (base64-encoded JSON) | Set/read on |
|---|---|---|---|
| `PAYMENT-REQUIRED` | server → client | `PaymentRequired` | `/purchase`'s `402` response |
| `PAYMENT-SIGNATURE` | client → server | `PaymentPayload` | `/pay`'s request (optional — see below) |
| `PAYMENT-RESPONSE` | server → client | `SettlementResponse` | `/pay`'s `200` and its `404` (unknown/used `terms_reference`) responses |

`PAYMENT-SIGNATURE` on `/pay` is **optional**, not required — the
existing JSON body (`terms_reference`, `approval_token`, `buyer_agent_id`)
remains the actual source of truth Phase 4a/4b clients already send. If a
client sends the header too, the server decodes it and requires its
`payload.terms_reference` / the token it references to agree with the
JSON body's — a defense-in-depth cross-check, not a new way to bypass the
existing verification. A client that never sends the header is unaffected.

---

## Purchase (the x402 step)

### `POST /agent/v1/purchase`

**Requires authentication.** Declares intent to buy. **This endpoint
never completes a purchase and never returns `200`** — it always
responds `402 Payment Required` with the terms that must be satisfied at
`/agent/v1/pay`. This is deliberate: it is the core of the x402-shaped
pattern this interface follows. There is no code path where a purchase
attempt bypasses this step.

Request:
```json
{
  "product_id": 1,
  "quantity": 1,
  "buyer_agent_id": "acme-shopping-bot",
  "approval_token": "5be3ae9c...64 hex chars..."
}
```

`approval_token` is optional — omit it (or send `null`) for a full-price
purchase. If present, it is recorded for audit purposes but is **not**
verified at this step (see below).

Response (`402`):
```json
{
  "amount": 249900,
  "currency": "INR",
  "accepted_payment_methods": ["razorpay_order"],
  "payment_endpoint": "/agent/v1/pay",
  "terms_reference": "8f3e2a1c-...-uuid4"
}
```

**Important:** `amount` here is always the **full listed price**
(`unit price × quantity`), regardless of whether `approval_token` was
supplied. This endpoint quotes "what it costs to buy this outright" —
it does not re-derive or preview a negotiated price (doing so would
require consuming the approval_token here, which would burn it before
payment actually happens). If you already negotiated a price via
`/negotiate`, you already know that number from that response; supply
the same `approval_token` again at `/pay` and the *actual* charge will
reflect it, verified fresh at that point.

`terms_reference` is a single-use reference to this specific purchase
intent (product, quantity, buyer identity). It expires the moment `/pay`
successfully uses it — a second `/pay` call with the same reference fails.
It is also bound to the buyer identity that created it: presenting a
`terms_reference` at `/pay` under a *different* authenticated
`buyer_agent_id` than the one that created it fails exactly the same way
an unknown or already-used reference does (`404` — we don't distinguish
the two, so as not to confirm or deny another agent's activity to you).

Errors: `401`, `403`, `404` (product not found), `400` (insufficient stock).

**As of Phase 8**, this `402` response also carries a `PAYMENT-REQUIRED`
header — base64-encoded JSON, x402 V2's `PaymentRequired` shape. See
"x402 V2 Conformance and Its Limits" above for what its fields actually
mean here. The JSON body above is unchanged and remains the
backward-compatible source of truth; the header is additive.

### `POST /agent/v1/pay`

**Requires authentication.** Completes the purchase: creates a real
Razorpay order (test-mode) using the exact same order-creation code path
and `approval_token` verification the human checkout flow uses. No
separate, weaker verification exists for this channel.

Request:
```json
{
  "terms_reference": "8f3e2a1c-...-uuid4",
  "approval_token": "5be3ae9c...64 hex chars...",
  "buyer_agent_id": "acme-shopping-bot"
}
```

`approval_token` is optional — omit for a full-price purchase at the
amount quoted by `/purchase`. **This is the value that's actually
verified and consumed** (not whatever was declared back at `/purchase`,
if anything). It must independently verify against the policy-gate's own
record — a missing, invalid, expired, already-used, or terms-mismatched
token all silently fall back to the full listed price. This never errors
and never charges what the caller merely claims.

Response (`200`):
```json
{
  "order_id": 7,
  "razorpay_order_id": "order_TTY1nF3ESyFR6x",
  "status": "created",
  "amount": 224910
}
```

`status` reflects the `Order` row's status at creation time — always
`"created"` from this endpoint (it becomes `"paid"` or `"failed"` later,
asynchronously, via Razorpay's webhook — see order status below).

Errors: `401`, `403`, `404` (unknown or already-used `terms_reference`),
`400` (insufficient stock, re-checked at this step since time may have
passed since `/purchase`).

**As of Phase 8**, this endpoint optionally accepts a `PAYMENT-SIGNATURE`
request header (base64-encoded `PaymentPayload`) alongside the JSON body
above, and always attaches a `PAYMENT-RESPONSE` header (base64-encoded
`SettlementResponse`) to both the `200` success case and the `404`
unknown/used-`terms_reference` case — not to `401`/`403`, which are
pre-settlement auth failures. See "x402 V2 Conformance and Its Limits"
above, including what `SettlementResponse.transaction` actually is (a
Razorpay order id, not a blockchain transaction hash).

---

## Order status

### `GET /agent/v1/order/{order_id}/status`

No authentication required (see the stated limitation at the top of this
document).

Response (`200`):
```json
{
  "order_id": 7,
  "status": "created",
  "amount": 224910,
  "razorpay_order_id": "order_TTY1nF3ESyFR6x"
}
```

`status` is one of `"created"`, `"paid"`, `"failed"` — the same lifecycle
Phase 1's webhook handler drives for human orders. There is no
payment-completion webhook exposed to agent buyers in this phase; poll
this endpoint.

Errors: `404` — order id doesn't exist.

---

## The full flow, end to end

```
1. POST /agent/v1/register          → obtain buyer_agent_id + api_key (once)
2. GET  /agent/v1/catalog           → browse products
3. POST /agent/v1/negotiate         → (optional) propose terms, get approval_token if approved
4. POST /agent/v1/purchase          → always 402, get terms_reference
5. POST /agent/v1/pay               → pay (with approval_token if negotiated), get order_id
6. GET  /agent/v1/order/{id}/status → poll until "paid" or "failed"
```

Step 3 is optional — a buyer agent can go straight from browsing to
`/purchase` → `/pay` for a full-price purchase, omitting `approval_token`
throughout.

`quantity` must be a positive integer (`> 0`) everywhere it appears
(`/negotiate`, `/purchase`) — zero or negative values are rejected with
`422` by request validation, before any endpoint logic runs. The same
applies to `proposed_terms.value`, which must be `> 0`.

## Audit trail

Every write action on this interface is recorded in the same audit log
and hash chain the human negotiation and checkout flows use — there is no
separate logging system for this channel. Event types you'll see
correlated to an agent-buyer transaction: `agent_negotiate_requested`,
`agent_negotiate_decided`, `gate_call`, `gate_decision`,
`agent_purchase_402`, `checkout_token_rejected` (only if a bad token was
presented), `order_created`. This audit trail is internal to the
merchant's systems — it is not exposed via this interface, and a buyer
agent has no way to read it.

## Example curl session

See `docs/agent-commerce-interface.curl-session.md` for a captured,
real request/response session exercising every endpoint above, run
against a live instance of this backend before any buyer-agent code
existed.
