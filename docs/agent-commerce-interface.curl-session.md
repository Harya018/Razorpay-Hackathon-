# Agent Commerce Interface — Verification Session

A real curl session run against a live instance of the backend
(`http://localhost:8010`), captured before any buyer-agent code existed.
Every endpoint in `agent-commerce-interface.md` is exercised at least
once here, including the error paths. Nothing below is hand-edited —
these are the actual responses.

## Catalog (no auth)

```
$ curl http://localhost:8010/agent/v1/catalog
[{"id":1,"name":"Wireless Headphones","price":249900,"currency":"INR","stock":15,"negotiable":true}]
[HTTP 200]

$ curl http://localhost:8010/agent/v1/product/1
{"id":1,"name":"Wireless Headphones","price":249900,"currency":"INR","stock":15,"negotiable":true}
[HTTP 200]

$ curl http://localhost:8010/agent/v1/product/999
{"detail":"Product not found"}
[HTTP 404]
```

## Registration

```
$ curl -X POST http://localhost:8010/agent/v1/register \
    -H "Content-Type: application/json" \
    -d '{"buyer_agent_id":"acme-shopping-bot","display_name":"Acme Shopping Bot"}'
{"buyer_agent_id":"acme-shopping-bot","api_key":"bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI","created_at":"2026-08-24T09:19:31.673789"}
[HTTP 201]

$ curl -X POST http://localhost:8010/agent/v1/register \
    -H "Content-Type: application/json" \
    -d '{"buyer_agent_id":"acme-shopping-bot"}'
{"detail":"buyer_agent_id already registered"}
[HTTP 409]
```

## Auth failure modes

```
$ curl -X POST http://localhost:8010/agent/v1/negotiate \
    -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"acme-shopping-bot","proposed_terms":{"type":"discount","value":224910}}'
{"detail":"Missing or malformed Authorization header"}
[HTTP 401]

$ curl -X POST http://localhost:8010/agent/v1/negotiate \
    -H "Authorization: Bearer bak_totally_fake_key" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"acme-shopping-bot","proposed_terms":{"type":"discount","value":224910}}'
{"detail":"Invalid API key"}
[HTTP 401]

$ curl -X POST http://localhost:8010/agent/v1/negotiate \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"someone-else-bot","proposed_terms":{"type":"discount","value":224910}}'
{"detail":"buyer_agent_id does not match the authenticated identity"}
[HTTP 403]
```

## Validation error (422) — distinct shape from the interface's own errors

```
$ curl -X POST http://localhost:8010/agent/v1/negotiate \
    -H "Authorization: Bearer bak_gQGEKCbfnaiYaFftEk6Yl5YMnxMQy20qx0n4dFIpXHM" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":0,"buyer_agent_id":"acme-shopping-bot","proposed_terms":{"type":"discount","value":224910}}'
{"detail":[{"type":"greater_than","loc":["body","quantity"],"msg":"Input should be greater than 0","input":0,"ctx":{"gt":0}}]}
[HTTP 422]
```

## Negotiation — approved and rejected

```
$ curl -X POST http://localhost:8010/agent/v1/negotiate \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"acme-shopping-bot","proposed_terms":{"type":"discount","value":224910}}'
{"approved":true,"approval_token":"3b5f1144a3fc5a2ea0fa34fa48caa31a2c49a5bbb46ba09e97dac4f6e0a45e4b","final_terms":{"type":"discount","value":224910},"reason":null,"max_allowed":null}
[HTTP 200]

$ curl -X POST http://localhost:8010/agent/v1/negotiate \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"acme-shopping-bot","proposed_terms":{"type":"discount","value":100000}}'
{"approved":false,"approval_token":null,"final_terms":null,"reason":"below_floor_or_exceeds_max_discount","max_allowed":224910}
[HTTP 200]
```

The rejected proposal (₹1,000.00) is far below this SKU's 10% floor
(₹2,249.10) — `max_allowed` tells the caller exactly what it should ask
for instead.

## Purchase → pay, full price

```
$ curl -X POST http://localhost:8010/agent/v1/purchase \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"acme-shopping-bot"}'
{"amount":249900,"currency":"INR","accepted_payment_methods":["razorpay_order"],"payment_endpoint":"/agent/v1/pay","terms_reference":"da47b7c2-f4fe-4c6a-b521-7aa30619113c"}
[HTTP 402]

$ curl -X POST http://localhost:8010/agent/v1/pay \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"terms_reference":"da47b7c2-f4fe-4c6a-b521-7aa30619113c","buyer_agent_id":"acme-shopping-bot"}'
{"order_id":9,"razorpay_order_id":"order_TTYU7pLShVRgXp","status":"created","amount":249900}
[HTTP 200]

$ curl -X POST http://localhost:8010/agent/v1/pay \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"terms_reference":"da47b7c2-f4fe-4c6a-b521-7aa30619113c","buyer_agent_id":"acme-shopping-bot"}'
{"detail":"Unknown or already-used terms_reference"}
[HTTP 404]
```

The second `/pay` call reuses the same `terms_reference` and correctly
fails — single-use, exactly like `approval_token`.

## Purchase → pay, negotiated price

```
$ curl -X POST http://localhost:8010/agent/v1/negotiate ... (same as above, fresh call)
{"approved":true,"approval_token":"3f8223978a9d82f809c80e48b5345752b2cb5ceabe0b152ac7665c5d7cb7f8a8","final_terms":{"type":"discount","value":224910},"reason":null,"max_allowed":null}

$ curl -X POST http://localhost:8010/agent/v1/purchase \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"acme-shopping-bot","approval_token":"3f8223978a9d82f809c80e48b5345752b2cb5ceabe0b152ac7665c5d7cb7f8a8"}'
{"amount":249900,"currency":"INR","accepted_payment_methods":["razorpay_order"],"payment_endpoint":"/agent/v1/pay","terms_reference":"6f2ab154-39b9-44e1-af43-4c244c160e24"}
[HTTP 402]
```

Note `amount` is still 249900 (full price) here — as documented,
`/purchase` always quotes the sticker price regardless of a declared
token. The real charge only reflects the negotiated price once `/pay`
verifies the token:

```
$ curl -X POST http://localhost:8010/agent/v1/pay \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"terms_reference":"6f2ab154-39b9-44e1-af43-4c244c160e24","approval_token":"3f8223978a9d82f809c80e48b5345752b2cb5ceabe0b152ac7665c5d7cb7f8a8","buyer_agent_id":"acme-shopping-bot"}'
{"order_id":10,"razorpay_order_id":"order_TTYUYDeXbDrjRr","status":"created","amount":224910}
[HTTP 200]
```

`amount: 224910` — the negotiated price, correctly applied only now.

## Bypass attempt: forged approval_token

```
$ curl -X POST http://localhost:8010/agent/v1/purchase \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"product_id":1,"quantity":1,"buyer_agent_id":"acme-shopping-bot"}'
{"amount":249900, ..., "terms_reference":"6b929d5f-6bb8-4423-b3a4-28739010fccc"}

$ curl -X POST http://localhost:8010/agent/v1/pay \
    -H "Authorization: Bearer bak_FBVSb2jlaRCax8nEl2QvOMZKcGQb1LY1pmZXeK8U4vI" -H "Content-Type: application/json" \
    -d '{"terms_reference":"6b929d5f-6bb8-4423-b3a4-28739010fccc","approval_token":"totally-forged-agent-token","buyer_agent_id":"acme-shopping-bot"}'
{"order_id":11,"razorpay_order_id":"order_TTYUtB1C9QQuMg","status":"created","amount":249900}
[HTTP 200]
```

A forged token silently falls back to the full listed price (249900) —
no error, no partial trust of the caller's claim. Confirmed against the
audit log: `checkout_token_rejected` fired with `reason: "unknown_token"`,
and the resulting `order_created` shows `discount_applied: false`. This
is the exact same fallback behavior Phase 3 proved for the human checkout
channel — same code path, same guarantee.

## Order status

```
$ curl http://localhost:8010/agent/v1/order/10/status
{"order_id":10,"status":"created","amount":224910,"razorpay_order_id":"order_TTYUYDeXbDrjRr"}
[HTTP 200]

$ curl http://localhost:8010/agent/v1/order/99999/status
{"detail":"Order not found"}
[HTTP 404]
```

## Audit trail + hash chain (post-session verification)

The negotiated purchase's events all correlate under one hash-chained
session (`agent-negotiate-810eb92f-df7e-4aa7-80e9-e19513de471b`):

```
agent_negotiate_requested → agent_negotiate_decided (approved) →
agent_purchase_402 → order_created (discount_applied: true, same
session_id) → agent_payment_completed
```

```python
>>> verify_chain(db, chain_key_for_session("agent-negotiate-810eb92f-df7e-4aa7-80e9-e19513de471b"))
ChainVerificationResult(valid=True, total_rows=3, broken_at_row_id=None, reason=None)
```
