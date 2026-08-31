# Agent-Readable Catalog Interface — README

`GET /agent/v1/catalog`, `GET /agent/v1/product/{id}`, and the payment
flow they lead into (`/agent/v1/negotiate` → `/agent/v1/purchase` →
`/agent/v1/pay`) — this is the interface an autonomous buyer agent talks
to. This README states plainly what settlement actually is here, before
an agent (or a judge) reads any further.

## The honesty boundary — read this first

**Settlement is processed via Razorpay (India, fiat, test-mode). This is
not an onchain settlement network.** Every product in this catalog
settles the same way: a Razorpay order is created, the customer (or
their agent's authorized payment flow) pays through Razorpay's
test-mode rails, and the merchant is paid in INR. Nothing in this
system moves a token, calls a smart contract, or touches a blockchain
of any kind.

This interface uses the **x402 V2 wire format** — the header names, the
base64-JSON encoding, the `PaymentRequirements`/`PaymentRequired`/
`PaymentPayload`/`SettlementResponse` object shapes all match the real
[x402 V2 specification](https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md)
field-for-field (see `docs/x402-conformance-diff.md` for the exact,
line-by-line checklist, and `x402_conformance_test.py` for the live,
re-runnable proof). **Wire-format conformance and settlement-model
conformance are two different claims, and only the first one is true
here.** x402 V2's real networks are onchain by construction — a CAIP-2
identifier like `eip155:8453` implies a counterparty can independently
verify settlement against a public chain. This merchant cannot make
that claim, and does not.

## Where this shows up in the actual API, not just this doc

1. **Every catalog item carries it directly.** `GET /agent/v1/catalog`'s
   response includes `"settlement_type": "fiat"` on every item — an
   agent sees this before it ever reaches a payment endpoint, not buried
   in payment-flow objects three requests later.
2. **The discovery endpoint states it in full.** `GET /agent/v1/discovery`
   returns the complete disclaimer sentence (below) in
   `extensionDisclaimer`, fetchable before an agent transacts at all.
3. **The payment-required response uses it as the network identifier.**
   `PAYMENT-REQUIRED`'s `accepts[].network` is `"inr-fiat:razorpay-test"`
   — CAIP-2-**shaped** (`namespace:reference`) but deliberately **not** a
   registered CAIP-2 namespace, so it can never be confused with
   `eip155:` or `solana:`. This is x402 V2's own formal Extensions
   mechanism at work, not an undocumented side channel — the same
   disclaimer is also carried in `PAYMENT-REQUIRED`'s `extensions.info`
   object, machine-discoverable via the spec's real mechanism, not just
   prose.
4. **The settlement response states it explicitly.** `PAYMENT-RESPONSE`
   always carries `"settlementType": "fiat-custodial"`, never
   `"onchain"`.

## The disclaimer, verbatim

This exact sentence appears in `GET /agent/v1/discovery`'s
`extensionDisclaimer` field, in `docs/agent-commerce-interface.openapi.v2.json`'s
`info.description`, and in `docs/x402-v2-conformance.md`:

> Settlement is processed via Razorpay (India, fiat, test-mode). This is
> not an onchain settlement network. network values under the `inr-fiat:`
> prefix are a documented x402 extension for this deployment, not part of
> the core x402 network registry.

## What "approval" actually means here

`PaymentPayload.payload.custodialReceipt` is this deployment's
substitute for x402's real `signature` + `authorization` fields on the
EVM "exact" scheme. There is no cryptographic signature anywhere in this
flow. `approval_token` is the policy-gate's own single-use, buyer-bound
approval, independently re-verified server-side against the gate's own
record on every redemption — never merely trusted because a client
presents it. That is the same real guarantee a signed authorization
provides in real x402 (an independently checkable authorization),
delivered through this deployment's actual mechanism instead of a
fabricated one.

## What this interface does NOT claim

- No real wallet-based identity or SIWx — there is no wallet.
- No multi-facilitator selection — exactly one settlement rail exists
  (Razorpay test-mode).
- No actual onchain settlement path, now or planned for this deployment.

If asked to demo "true" x402 compliance, the honest answer is: **wire-format
conformant, settlement-model divergent by design, documented as such** —
that sentence is the answer, not a hedge.

## Further reading

- `docs/x402-conformance-diff.md` — the field-by-field checklist this
  conformance pass was built from.
- `docs/x402-v2-conformance.md` — the fuller narrative (backward
  compatibility decisions, adversarial verification, frozen-spec
  versioning).
- `docs/agent-commerce-interface.md` — the full REST contract.
- `docs/agent-commerce-interface.openapi.v2.json` — the machine-readable
  spec, versioned separately from the frozen v1.0.1 file.
- `x402_conformance_test.py` (in `redteam/`) — run it yourself against a
  live instance of this service; every check prints its own pass/fail,
  not one aggregate number.
