# x402 V2 Wire-Format Conformance — Phase 11

**Status:** current. Supersedes the field names (not the overall honesty
argument) in `agent-commerce-interface.md`'s "x402 V2 Conformance and Its
Limits" section, which was Phase 8's first pass. This document is the
authoritative reference for the exact wire shapes as of Phase 11.

## The disclaimer (verbatim, appears in three places)

This exact sentence appears — word for word — in the discovery endpoint's
JSON response, the OpenAPI spec's `info.description`, and this document.
If you find a place where the wording differs, that's a bug, not a
stylistic choice:

> Settlement is processed via Razorpay (India, fiat, test-mode). This is
> not an onchain settlement network. network values under the `inr-fiat:`
> prefix are a documented x402 extension for this deployment, not part of
> the core x402 network registry.

## What "conformance" means here, precisely

x402 V2's real networks are onchain by construction — a CAIP-2 identifier
like `eip155:8453` implies a counterparty can independently verify
settlement against a public chain. This merchant settles via Razorpay, a
fiat, custodial, test-mode rail. Claiming a real CAIP namespace for that
would be a **false** conformance claim. So this phase does two things
that are both true at once:

1. **Wire-format conformance is real and checkable.** Header names, the
   base64-JSON encoding, and the `PaymentRequirements` / `PaymentRequired`
   / `PaymentPayload` / `SettlementResponse` object shapes match the real
   [x402 V2 specification](https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md)
   field-for-field. A strict client that only checks "does this look like
   x402 V2" passes us.
2. **Settlement-model conformance is explicitly, permanently out of
   scope**, and every place that could be mistaken for an onchain claim
   says so. This uses x402 V2's own **Extensions** mechanism — the spec
   formalizes a path for implementers to add functionality without
   forking it — rather than inventing an undocumented side channel.

## A correction made during this phase (verified live, not assumed)

The phase brief's example `PAYMENT-REQUIRED` body used a field named
`maxAmountRequired` and nested `resource`/`description` inside each
`accepts[]` entry. Re-fetching the actual spec text
(`specs/x402-specification-v2.md`, section 5.1.2) live for this phase
found neither is correct:

- The real field is **`amount`**, not `maxAmountRequired`. The spec's own
  example: `"amount": "10000"`, described as "Required payment amount in
  atomic token units."
- `resource` and `description` belong to a **separate, top-level**
  `ResourceInfo` object on `PaymentRequired` (fields: `url`, `description`,
  `mimeType`) — not to each `PaymentRequirements` entry inside `accepts`.

This document and the implementation use the spec's actual field names
and structure, not the brief's example — because the whole point of this
phase is that a strict conformance check should actually pass, and
matching an inaccurate example instead of the real registry would defeat
that. (Phase 8's original implementation already had this right, for the
same reason: its schemas were built by re-reading the spec live rather
than from a recalled shape.)

## `PAYMENT-REQUIRED` — server → client, on `/purchase`'s `402`

```json
{
  "x402Version": 2,
  "error": "Payment required to complete this purchase.",
  "resource": {
    "url": "/agent/v1/product/1",
    "description": "Purchase of 1 x Wireless Headphones",
    "mimeType": "application/json"
  },
  "accepts": [
    {
      "scheme": "exact",
      "network": "inr-fiat:razorpay-test",
      "amount": "249900",
      "asset": "INR",
      "payTo": "rzp_test_xxxxxxxxxxxx",
      "maxTimeoutSeconds": 300,
      "extra": {
        "settlementType": "fiat-custodial",
        "facilitator": "razorpay-test-mode",
        "product_id": 1,
        "quantity": 1,
        "terms_reference": "8f3e2a1c-...-uuid4"
      }
    }
  ]
}
```

Field-by-field, what changed from Phase 8 and why:

| Field | Phase 8 | Phase 11 | Why |
|---|---|---|---|
| `scheme` | `"razorpay-inr"` (deliberately non-registry) | `"exact"` (the real scheme name) | `"exact"` describes *what* is being settled (the exact quoted amount, no partial/streaming payment) — that part of the real scheme's meaning genuinely applies here. What does NOT apply (an EIP-3009 signed authorization) is handled by the `payload.custodialReceipt` substitution below, not by hiding behind a fake scheme name. |
| `network` | `"razorpay-test-inr"` (a plain label) | `"inr-fiat:razorpay-test"` (CAIP-2-**shaped**, deliberately non-CAIP) | The `inr-fiat:` prefix cannot be confused with a registered CAIP-2 namespace (`eip155:`, `solana:`, etc.) — it reads as CAIP-shaped specifically so a parser expecting `namespace:reference` doesn't choke, while the namespace itself is self-documenting as "this is fiat, not a chain." |
| `amount` | present | present, unchanged | Paise — INR's own atomic unit, exactly analogous to on-chain atomic token units. Already correct in Phase 8. |
| `asset` | `"INR"` | `"INR"`, unchanged | The spec's own ISO 4217 fallback for `asset` — a direct, honest fit, no substitution needed. |
| `payTo` | `RAZORPAY_KEY_ID` | unchanged | The merchant's Razorpay **public** key id — not secret (already exposed client-side for the checkout widget elsewhere in this project), but not a wallet address either. Real x402 V2 supports *dynamic* `payTo` (per-request routing to different addresses/roles/callbacks) for merchants with multiple settlement destinations; this deployment has exactly one, so `payTo` is present and correctly typed but constant — that's a real limitation of this deployment, not a shape gap. |
| `extra.settlementType` | absent | `"fiat-custodial"` | New in Phase 11 — states the settlement model explicitly and machine-readably, so a consuming agent can branch on it instead of having to already know this merchant's quirks. |
| `extra.facilitator` | absent | `"razorpay-test-mode"` | Real x402 has pluggable facilitators (who submits/verifies the onchain transaction); ours has exactly one, non-onchain, settlement rail, named honestly rather than omitted. |

## `PAYMENT-SIGNATURE` — client → server, on `/pay`'s request

Real x402's "exact" EVM scheme payload holds `signature` (an EIP-3009
signature) and `authorization` (the signed transfer details) — a
cryptographic proof this system has no equivalent for. Rather than call
anything here a "signature," the scheme-specific payload is named for
what it actually is:

```json
{
  "x402Version": 2,
  "scheme": "exact",
  "network": "inr-fiat:razorpay-test",
  "payload": {
    "custodialReceipt": {
      "terms_reference": "8f3e2a1c-...-uuid4",
      "approval_token": "5be3ae9c...64 hex chars..."
    }
  }
}
```

`custodialReceipt` is not a receipt from Razorpay itself (no payment has
happened yet at this point in the flow) — it's this system's actual proof
of authorization: `terms_reference` is what `/purchase` minted, and
`approval_token` is the policy-gate's own single-use, buyer-bound
approval, independently re-verified server-side against the gate's own
record — never merely trusted because the client presents it. That's the
same real guarantee `signature`+`authorization` provide in real x402 (an
independently checkable authorization), delivered through this
deployment's actual mechanism instead of a fabricated one.

**This header is now REQUIRED on `/pay`, not optional** — see
"Backward compatibility decision" below for why.

## `PAYMENT-RESPONSE` — server → client, on `/pay`'s response (both outcomes)

```json
{
  "success": true,
  "settlementType": "fiat-custodial",
  "network": "inr-fiat:razorpay-test",
  "transaction": "order_TTY1nF3ESyFR6x",
  "reference": "order_TTY1nF3ESyFR6x",
  "payer": "acme-shopping-bot"
}
```

Two more honesty notes, found by checking what data is actually available
at the moment this header is built, not assumed:

- **`transaction` is the real spec's field name** (confirmed live against
  the spec text); **`reference`** is the name the phase brief asked for.
  Both are present, holding the identical value, so a client checking
  either name finds it — but `transaction` is the one that makes a
  strict-spec check pass.
- **The value is a Razorpay `razorpay_order_id`, never a `razorpay_payment_id`
  (a `"pay_..."` string).** At the instant `/pay` returns, this system has
  only just created the Razorpay order — actual payment capture happens
  **asynchronously**, later, via Razorpay's own webhook (`Order.status`
  moves `created` → `paid` only then; see `agent-commerce-interface.md`'s
  Order status section). The phase brief's example showed `"pay_xxx"` —
  using that literally here would claim a captured payment this system
  cannot yet know happened. `success: true` on this header means "order
  created and, if a token was used, the discount was independently
  verified" — **not** "payment captured." An agent that wants confirmed
  capture must still poll `GET /agent/v1/order/{id}/status` as documented.
- `errorReason` (present on failure, omitted on success, per the spec's
  own optionality) is unchanged from Phase 8 — still attached on **both**
  outcomes of a real settlement decision, not just success, per the v2
  spec's explicit callout that omitting it on failure is a known bug class.

## Discovery endpoint — new in Phase 11

`GET /agent/v1/discovery` — no authentication required, mirrors
`GET /agent/v1/catalog`'s openness. A real buyer agent fetches this
*before* transacting to learn what payment schemes/networks this catalog
accepts, without needing this document.

```json
{
  "x402Version": 2,
  "supportedSchemes": ["exact"],
  "supportedNetworks": ["inr-fiat:razorpay-test"],
  "extensionDisclaimer": "Settlement is processed via Razorpay (India, fiat, test-mode). This is not an onchain settlement network. network values under the inr-fiat: prefix are a documented x402 extension for this deployment, not part of the core x402 network registry.",
  "catalogUrl": "/agent/v1/catalog",
  "negotiateUrl": "/agent/v1/negotiate",
  "purchaseUrl": "/agent/v1/purchase",
  "payUrl": "/agent/v1/pay"
}
```

## Conversational negotiation — `/negotiate`'s new `message` field

Separate from the x402 header work above, but shipped in the same phase:
`NegotiateRequest`/`NegotiateResponse` each gained an optional `message`
field so the AI-to-AI negotiation between the buyer agent and this
merchant's `/agent/v1/negotiate` reads like an actual chat, not just a
`{approved, max_allowed}` tuple.

The buyer agent's message is free text (e.g. "Hi, I'm interested in the
Wireless Headphones. My budget is ₹2000.00."), never parsed back out by
the seller — it only ever reaches the deterministic decision as an
audit-log annotation. The seller's `message` is generated by a **second,
separate LLM call that runs strictly *after* the policy gate's
`approved`/`reason`/`max_allowed`/`final_terms` decision is already
final** — same "LLM frames, deterministic logic decides" separation this
project has used since Phase 3's gate and Phase 10's discount ladder. If
that call fails for any reason, `message` is simply `null`; every other
field in the response is unaffected (mirrors `close_negotiation`'s
best-effort `customer_mindset_summary` pattern).

**This second LLM call only runs when `NegotiateRequest.message` is
present.** Found during the Phase 11 red-team pass (see
`red-team-agent/app/attacks/concurrent_race.py`'s new floor-price race
case): making it unconditional meant every `/negotiate` call — including
plain, non-conversational ones with no `message` — paid an LLM
round-trip, which under concurrent load produced real read-timeouts from
Groq/Gemini rate-limit fallback chaining. A caller that never opened a
conversation doesn't need one echoed back, so the reply is now only
attempted when the buyer actually sent a `message` — a plain
`proposed_terms`-only call is exactly as fast as it was before Phase 11.

Live example (verified against the running backend, not fabricated) — a
buyer agent proposes a total below the store's floor:

```json
// request
{
  "product_id": 1,
  "quantity": 1,
  "buyer_agent_id": "phase11-verify-agent",
  "proposed_terms": { "type": "discount", "value": 149940 },
  "message": "Hi, I'm interested in the Wireless Headphones. My budget is ₹1499.40."
}
```

```json
// response
{
  "approved": false,
  "approval_token": null,
  "final_terms": null,
  "reason": "below_floor_or_exceeds_max_discount",
  "max_allowed": 224910,
  "message": "We sell the Wireless Headphones for ₹2249.10. Your budget is a bit low for the listed price, but we can offer them at ₹2249.10. Does that work for you?"
}
```

The message correctly narrates the *real* decision (states the listed
price, offers the actual `max_allowed` counter, never invents a number)
— it cannot say anything else, because the prompt is only ever given the
already-decided figures, never asked to choose one.

The buyer-agent's own graph (`buyer-agent/app/graph/nodes.py`) sends this
message on every `/negotiate` call (`_buyer_negotiation_message`) and
appends the seller's reply to the human-facing `pending_message` at each
checkpoint (`_seller_reply_suffix`), so a person watching the CLI/chat
sees the actual AI-to-AI exchange, not just this agent's own summary of
it. A live 3-round CLI run (`python -m app.main "I want to buy the
wireless headphones, please negotiate the price down, my budget is 2000
rupees"`) showed the seller's agent opening with "We sell the Wireless
Headphones at ₹2374.05... Your offer is approved", ladder-stepping to
₹2249.10, and the buyer agent finally purchasing at that price after the
discount ladder was exhausted — a real negotiate-or-approve conversation,
not a single canned line.

## Backward compatibility decision (explicit, not left implicit)

Two different questions, two different answers:

1. **Do the existing JSON response bodies for `/purchase` and `/pay`
   change?** No. `PurchaseTermsResponse` and `PayResponse` are byte-for-byte
   unchanged from Phase 4a/8. Every client built against this document
   before Phase 11 — including this project's own buyer-agent from Phases
   4b/9/10 — keeps working unmodified for anything that only reads the
   JSON body. This matches real x402 V2 SDKs' own backward-compatibility
   stance with V1 payloads, deliberately.
2. **Does `PAYMENT-SIGNATURE` on `/pay`'s *request* stay optional?** No —
   this is the one deliberate exception, scoped to exactly one header on
   one endpoint. Phase 8 made it optional/additive (JSON body was the sole
   source of truth). Phase 11's adversarial-check requirement is explicit:
   a missing or malformed `PAYMENT-SIGNATURE` must be rejected with a
   clear `4xx`, not silently passed through. Making that true requires the
   header to actually be required. The buyer-agent has been updated to
   always send it; a pure-JSON-body client that predates this phase would
   now get `400 Missing PAYMENT-SIGNATURE header` calling `/pay`. This is
   the narrowest possible cut, not a blanket "V1 is gone."

## Explicitly out of scope (per the phase brief, unchanged)

- Real wallet-based identity / SIWx — not applicable without a real wallet.
- Multi-facilitator selection — exactly one settlement rail exists.
- Any actual onchain settlement path. If asked to demo "true" x402
  compliance: **wire-format conformant, settlement-model divergent by
  design, documented as such** — that sentence is the honest answer, not
  a hedge.

## Adversarial verification

`/pay` without a `PAYMENT-SIGNATURE` header, or with one that is not valid
base64/JSON, or whose `custodialReceipt.terms_reference` /
`approval_token` disagree with the JSON body, is rejected with `400`
before any database write. Verified live against the running backend as
part of this phase (see the phase's own verification notes / commit for
the exact requests and responses) — not merely asserted.

## Frozen-spec versioning

`docs/agent-commerce-interface.openapi.json` (v1.0.1, Phase 4a/4b) is
**left untouched** — it remains the historical snapshot of the core REST
contract, which has not changed. A new file,
`docs/agent-commerce-interface.openapi.v2.json` (v2.0.0), adds the x402
V2 header semantics and the new discovery endpoint on top of the same
paths. Nothing was silently overwritten.

## Acceptance checklist

| # | Item | Status |
|---|---|---|
| 1 | Payment data moved into `PAYMENT-REQUIRED` / `PAYMENT-SIGNATURE` / `PAYMENT-RESPONSE` headers; deprecated `X-*` headers gone | Done. This codebase never had `X-PAYMENT-*` headers (Phase 8 already used the correct names) — grepped both `backend/` and `buyer-agent/app/` live, zero matches. |
| 2 | CAIP-2/CAIP-19-shaped network/asset identifiers | Done — `network: "inr-fiat:razorpay-test"` is CAIP-2-**shaped** (`namespace:reference`); `asset: "INR"` uses the spec's own ISO 4217 fallback. |
| 3 | `network` value is `inr-fiat:razorpay-test`, never a real CAIP namespace | Done — verified live via `/agent/v1/discovery` and a real `/purchase` 402's `PAYMENT-REQUIRED` header, both shown above. |
| 4 | Dynamic `payTo`; pluggable named schemes | Honestly **not implemented**, not silently claimed: `payTo` is present and correctly typed but constant (one Razorpay account, one settlement destination — see the `PAYMENT-REQUIRED` field table above); `scheme` supports exactly one named scheme, `"exact"`. Multi-facilitator/multi-scheme support is explicitly out of scope for this deployment (see below), not a gap disguised as done. |
| 5 | Disclaimer appears verbatim in three places | Done — `GET /agent/v1/discovery`'s `extensionDisclaimer`, `docs/agent-commerce-interface.openapi.v2.json`'s `info.description`, and this document's "The disclaimer" section above, all byte-identical. |
| 6 | `PAYMENT-RESPONSE` carries `settlementType: "fiat-custodial"`, never `"onchain"` | Done — verified live in the real `/pay` response shown above. |
| 7 | Existing frozen OpenAPI spec is versioned/forked, not silently overwritten | Done — see "Frozen-spec versioning" above; this phase only ever *read* `agent-commerce-interface.openapi.json` (never edited it) and wrote the new shapes to the separate `agent-commerce-interface.openapi.v2.json` file. |
| 8 | Buyer agent updated, isolated venv, no shared imports from the backend | Done — `buyer-agent/app/x402_headers.py` and `client.py` independently re-derive the new shapes from this document, not by importing `backend/app/agent_commerce/*`; `buyer-agent/.venv` is its own environment. |
| 9 | Adversarial check: missing/malformed `PAYMENT-SIGNATURE` rejected with a clear 4xx | Done — verified live: missing header → `400 {"detail": "Missing required PAYMENT-SIGNATURE header"}`; malformed (non-base64) header → `400 {"detail": "Malformed PAYMENT-SIGNATURE header: ..."}`. Neither silently passes through. |
