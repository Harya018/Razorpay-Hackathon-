# x402 V2 Conformance Diff — line-by-line checklist

**Status:** current. Written as a standalone, pre-code checklist per this
phase's own instruction — every row below was checked against the real
spec text (re-fetched live for this pass, not recalled) BEFORE any code
was changed, so "conformant" means something checkable, not a guess.

**Sources fetched live for this pass:**
- `https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md` (core schemas)
- `https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md` (HTTP header names/encoding)

This supersedes the field-shape claims in `docs/x402-v2-conformance.md`
(Phase 11's own pass) wherever they disagree — two real gaps were found
that Phase 11 missed. `docs/x402-v2-conformance.md` remains the fuller
narrative reference (disclaimer placement, backward-compatibility
decision, honesty-boundary discussion); this file is the field-by-field
checklist and the record of what changed in this pass specifically.

## Legend

- ✅ **Conformant** — matches the spec exactly, no substitution needed.
- ⚠️ **Deliberate substitution** — shape matches, meaning is honestly
  adapted for a fiat/custodial rail (documented, not hidden).
- ❌ **Gap (found this pass)** — a real mismatch, not previously caught,
  fixed as part of this same pass.
- 📝 **Documented limitation** — a known, disclosed scope boundary, not
  fixed (see reasoning per row).

---

## 1. `x402Version`

| Object | Spec | Before this pass | After this pass |
|---|---|---|---|
| PaymentRequired | required, `number`, must be 2 | ✅ present | ✅ unchanged |
| PaymentPayload | required, `number` | ✅ present | ✅ unchanged |
| DiscoveryResponse (not a core spec object — this deployment's own) | n/a | ✅ present | ✅ unchanged |

## 2. `PaymentRequired` (the 402 response body, `PAYMENT-REQUIRED` header)

| Field | Spec | Status |
|---|---|---|
| `x402Version` | required | ✅ |
| `error` | optional | ✅ |
| `resource` (`ResourceInfo`: `url` required, `description`/`mimeType` optional) | required, top-level object | ✅ — already correctly top-level, not nested inside `accepts[]` (Phase 11 caught this one) |
| `accepts` (array of `PaymentRequirements`) | required | ✅ |
| `extensions` (`{info: object, schema: object}`) | optional, but **formally defined** by the spec's own Extensions mechanism | ❌ **Gap, fixed this pass** — see §5 below |

### `PaymentRequirements` (each entry in `accepts[]`)

| Field | Spec | Status |
|---|---|---|
| `scheme` | required, string | ✅ `"exact"` — genuinely applies (settling the exact quoted amount, no partial/streaming payment) |
| `network` | required, CAIP-2 `namespace:reference` | ⚠️ `"inr-fiat:razorpay-test"` — CAIP-2-**shaped**, deliberately **not** a registered namespace (can't be confused with `eip155:`/`solana:`). See the verbatim disclaimer requirement. |
| `amount` | required, string, atomic units | ✅ paise, as a string — this is the spec's real field name (Phase 11 already caught that a task brief's example, `maxAmountRequired`, was wrong) |
| `asset` | required, string (contract address or ISO 4217) | ✅ `"INR"` — the spec's own fiat fallback, a direct fit |
| `payTo` | required, string (wallet address or role constant) | ⚠️ Razorpay **public** key id — not a wallet address, not secret |
| `maxTimeoutSeconds` | required, number | ✅ shape-conformant (`300`); not enforced server-side — documented, not hidden |
| `extra` | optional, scheme-specific | ✅ carries `settlementType`, `facilitator`, `product_id`, `quantity`, `terms_reference` |

## 3. `PaymentPayload` (the retried request, `PAYMENT-SIGNATURE` header)

| Field | Spec | Before this pass | After this pass |
|---|---|---|---|
| `x402Version` | required | ✅ | ✅ |
| `resource` | optional, `ResourceInfo` | *(absent)* | ✅ left optional/absent — not required, adds no value here |
| `accepted` (the **full, chosen** `PaymentRequirements` object) | **required** | ❌ **MISSING ENTIRELY.** The previous implementation had flattened, invented top-level `scheme`/`network` fields instead — a shape that resembled the spec but didn't match it. | ✅ **Fixed** — `accepted: PaymentRequirements` now required; production client (buyer-agent) echoes the real `accepts[0]` it received from the seller's own `PAYMENT-REQUIRED`, per the spec's actual flow ("client echoes what the server offered") |
| `payload` (scheme-specific) | required | ⚠️ | ⚠️ unchanged — see §4 |
| `extensions` | optional | ✅ | ✅ |

**This was the real finding of this pass** — not a substitution, an actual
shape bug. It slipped through Phase 11's own verification because that
pass tested the flow end-to-end and it "worked" (both sides agreed on the
same wrong shape), which is exactly why an independent, spec-first diff
catches things a working demo doesn't.

### `payload` contents for the "exact" EVM scheme vs. this deployment

| Spec field (EVM `exact` scheme) | This deployment | Why |
|---|---|---|
| `signature` (EIP-712 signature) | *(absent — replaced)* | No cryptographic signature exists in a custodial/fiat flow |
| `authorization.from/to/value/validAfter/validBefore/nonce` (EIP-3009) | *(absent — replaced)* | No onchain authorization exists |
| — | `custodialReceipt.terms_reference` + `custodialReceipt.approval_token` | ⚠️ **Deliberate substitution**, not a gap: `approval_token` is the policy-gate's own single-use, independently-verified authorization — the real functional equivalent of "proof this specific charge was authorized," delivered through this deployment's actual mechanism. Named `custodialReceipt`, never `signature`, so nothing implies cryptographic proof that doesn't exist. |

## 4. `SettlementResponse` (the final response, `PAYMENT-RESPONSE` header)

| Field | Spec | Status |
|---|---|---|
| `success` | required, boolean | ✅ |
| `errorReason` | optional | ✅ |
| `payer` | optional | ⚠️ `buyer_agent_id`, not a wallet address |
| `transaction` | **required**, string (blockchain tx hash; empty string if failed) | ⚠️ holds a Razorpay `razorpay_order_id`, **never** a `razorpay_payment_id` (`"pay_..."` string) — payment capture is asynchronous via webhook, so no payment id exists yet at the moment this header is built |
| `network` | required, CAIP-2 | ⚠️ same `inr-fiat:` substitution as §2 |
| `amount` | optional | ✅ |
| `extensions` | optional | ✅ |
| *(not a spec field)* `settlementType` | — | ⚠️ **added**, always `"fiat-custodial"`, never `"onchain"` — the honesty-boundary marker the spec has no field for, so one was added rather than silently omitted |
| *(not a spec field)* `reference` | — | Present alongside `transaction`, identical value — kept for a consuming client that looks for either name; `transaction` is what a strict spec check reads |

Header presence on both outcomes: the spec's own examples show
`PAYMENT-RESPONSE` present on both success **and** failure — ✅ already
matched (attached on every settlement decision, not just success).

## 5. Extensions mechanism — ❌ gap, fixed this pass

**Spec's actual definition** (re-fetched live, not assumed):

> "Extensions enable modular optional functionality beyond core payment
> mechanics. Servers advertise supported extensions in `PaymentRequired`,
> and clients echo them in `PaymentPayload`."

Formal shape: `extensions: {info: object, schema: object}` — `schema` is
a JSON Schema describing `info`'s structure.

**Before this pass:** this deployment only ever carried its honesty
disclaimer *informally* — as a network-namespace prefix (`inr-fiat:`)
plus a plain string on the `GET /agent/v1/discovery` endpoint. It never
populated the spec's own formal `extensions` object at all. That's not
wrong in spirit (the disclaimer was real and prominent), but it means a
client that specifically looks for the spec's Extensions mechanism would
find nothing there.

**Fixed this pass:** `PaymentRequired.extensions` now carries
`{info: {"inr-fiat": {"disclaimer": "<the exact sentence>"}}, schema:
{...}}` — the identical disclaimer, now also machine-discoverable via the
spec's own mechanism, not just prose. The discovery endpoint's
`extensionDisclaimer` field is unchanged (still there, still useful for a
client that hasn't transacted yet).

## 6. HTTP header names & encoding (transport spec, not the core spec)

Re-fetched live from the separate transport document, since the core
spec explicitly defers header names to it ("Transport-specific
implementations... covered in transport specifications").

| Header | Spec | Status |
|---|---|---|
| `PAYMENT-REQUIRED` | base64-encoded `PaymentRequired` JSON | ✅ |
| `PAYMENT-SIGNATURE` | base64-encoded `PaymentPayload` JSON | ✅ |
| `PAYMENT-RESPONSE` | base64-encoded `SettlementResponse` JSON | ✅ |
| Encoding | base64-encoded JSON for all three | ✅ |

No deprecated `X-*` header names exist anywhere in this codebase or its
buyer-agent/red-team clients — grepped live across `backend/`,
`buyer-agent/`, `red-team-agent/`, `redteam/`; zero matches.

## 7. HTTP status code usage — ❌ gap, fixed this pass

**Spec's stated mapping** (re-fetched live): 402 Payment Required is used
for **both** the initial payment-required signal **and** payment-failure
scenarios on the settlement call — not just the first 402.

**Before this pass:** `/agent/v1/pay`'s failure path (unknown or
already-used `terms_reference`) returned `404`. Reasonable REST
instinct, but not what the spec asks for on a payment-flow-specific
failure.

**Fixed this pass:** that specific failure now returns `402` (with
`PAYMENT-RESPONSE` still attached, `success: false`), matching
`PAYMENT-REQUIRED`'s own use of 402 earlier in the same flow. A
malformed/missing `PAYMENT-SIGNATURE` header stays `400` — that's a
transport-level parse failure, not a payment outcome, and the spec's own
example text literally uses `"PAYMENT-SIGNATURE header is required"` as
a 400-class error message, not a 402 one.

## 8. CAIP-2 / CAIP-19 identifiers

| Requirement | Spec | This deployment |
|---|---|---|
| `network` must be CAIP-2 `namespace:reference` | Required | ⚠️ shaped correctly, deliberately non-registry (see §2) |
| `asset` must be CAIP-19 | **Not required** — spec explicitly allows "token contract address **or ISO 4217 currency code for fiat**," no CAIP-19 mandate found in the document | ✅ `"INR"` is a direct, honest fit — no substitution needed here at all |

## 9. Settlement honesty boundary — not a spec field, a deployment-level decision

Not part of the wire-format spec at all, but explicitly required by this
phase: `settlement_type: "fiat"` is now present directly on every
`CatalogItem` in `GET /agent/v1/catalog` — an agent sees this **before**
it ever reaches a payment endpoint, not buried in payment-flow objects or
docs. See `docs/agent-commerce-catalog-README.md` for the full honesty
statement.

## Items explicitly NOT re-litigated this pass (already correct per Phase 11)

- `ResourceInfo` being top-level on `PaymentRequired`, not nested inside
  each `accepts[]` entry (Phase 11 already caught a task-brief example
  that had this wrong).
- `amount` being the real field name, not `maxAmountRequired`.
- `asset: "INR"` needing no substitution.
- `PAYMENT-RESPONSE` being attached on both success and failure.

## Summary table

| # | Item | Verdict |
|---|---|---|
| 1 | `x402Version` presence | ✅ Conformant |
| 2 | `PaymentRequired` shape | ✅ Conformant (was already correct) |
| 2 | `PaymentRequirements` shape | ✅ Conformant / ⚠️ documented substitutions |
| 3 | `PaymentPayload.accepted` | ❌→✅ **Real gap, fixed this pass** |
| 4 | `SettlementResponse` shape | ⚠️ Conformant with documented substitutions |
| 5 | Extensions mechanism | ❌→✅ **Real gap, fixed this pass** |
| 6 | HTTP header names/encoding | ✅ Conformant |
| 7 | 402 for payment-failure (not just payment-required) | ❌→✅ **Real gap, fixed this pass** |
| 8 | CAIP-2 network / CAIP-19 asset | ⚠️ documented substitution / ✅ no substitution needed |
| 9 | `settlement_type` in catalog response | ✅ Added this pass |

**Net result: 3 real, previously-uncaught gaps found and fixed in this
pass** (`PaymentPayload.accepted`, the formal Extensions object, 402 vs
404 for payment failure) — on top of what was already correct or already
honestly substituted from Phase 11. See `x402-conformance-results.json`
and `x402_conformance_test.py` for the live, re-runnable verification of
every row above.
