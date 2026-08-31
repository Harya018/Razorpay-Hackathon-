# What Broke, and How It Was Handled

This is a plain account of the real bugs found across this build —
including the ones a live red-team suite turned up against our own
running system. None of these were hidden or quietly patched; each one
changed how a later phase was designed, and several of the fixes are
still visible as comments in the code pointing back to the exact finding
that caused them. Read this as evidence of how bugs were found and closed
in this project, not as an apology list.

---

## 1. Audit hash-chain rows hashed differently before and after a reload (SQLite timezone normalization)

**What broke:** the audit log's tamper-evidence hash chain
(`backend/app/audit.py`) computes each row's `entry_hash` from, among
other fields, its own `created_at` timestamp. `created_at` is created as
a timezone-**aware** UTC `datetime` in Python
(`datetime.now(timezone.utc)`), but SQLite has no native timezone-aware
storage type — it round-trips `DateTime` columns as **naive** (it silently
drops `tzinfo` on write-then-read). That means: hash a row once
immediately after creating it (still holding the aware `datetime` object
in memory) and you get one hash; reload that same row from the database
later (now naive) and recompute the identical hash formula, and you get a
**different** hash for a row nobody tampered with — a false "tampered!"
positive purely from a storage round-trip, not a security issue anyone
introduced.

**How it was found:** exercising the independent chain verifier
(`verify_chain`) against rows that had actually been committed and
reloaded from disk, not just rows still living in the same in-memory
session that wrote them — the discrepancy only shows up across a real
write/read boundary, not on a same-process code path that never leaves
Python's own object.

**The fix:** `_entry_hash()` normalizes by stripping `tzinfo` from
`created_at` *before* hashing, on both the write path and the read-back
verify path (`created_at.replace(tzinfo=None).isoformat()`), so the exact
same row always hashes to the exact same value regardless of whether it's
still in memory or has round-tripped through SQLite. The comment
documenting this is still in the code, on the line that matters.

**Why it matters for a real payments system:** a hash chain that produces
false positives is worse than no hash chain at all — it trains an
operator to expect noise and start ignoring "chain broken" alerts, which
is exactly the failure mode that lets a *real* tamper event slip through
unnoticed later. Storage-layer quirks (timezone handling, float rounding,
column collation) are a classic, easy-to-miss source of that kind of
false positive in any audit/ledger system, not just this one.

---

## 2. Chat auto-scroll didn't reliably track new messages

**What broke:** the merchant dashboard's AI Buyer Agents chat view
(`frontend/src/components/dashboard/ChatThread.jsx`) needs to keep the
newest message in view as a conversation grows via SSE-pushed updates,
and reset to the bottom when a merchant switches to a different
conversation entirely. A naive one-time "scroll to bottom on mount"
doesn't re-fire on either of those triggers.

**The fix in place today:** a dedicated bottom-anchor element
(`bottomRef`) with `scrollIntoView({ behavior: "smooth", block: "end" })`,
inside a `useEffect` explicitly keyed on **both**
`group?.events?.length` (new message arrives) **and** `group?.group_key`
(merchant switches conversations) — so it re-scrolls on either trigger,
not just once.

**Why it matters for a real payments system:** less a payments-specific
lesson than a general one about live operational dashboards: an operator
watching a live feed needs the newest event to actually be visible
without manual scrolling, or a live view silently becomes a stale
snapshot the first time an alert-worthy event happens off-screen.

---

## 3. Product catalog images were random stock photography, not the actual products

**What broke:** the storefront's catalog images came from picsum.photos
(purely random placeholder photography, unrelated to any product's
category or name). Swapping in LoremFlickr (keyword-searchable stock
photos) as a fix attempt was tried and then **rejected after live visual
inspection** — one result for an unrelated Puma sneaker product returned
an actual photo of a real person's face, and another showed a real Nike
logo/shoebox for a competing brand's product. Both are unacceptable for
a live demo storefront, for different reasons (a real person's likeness;
a real competitor's trademark).

**The fix:** generated deterministic SVG placeholder images at seed time
(`backend/scripts/seed_catalog.py`), derived from each product's own
emoji/name/category, with a small per-category color palette. A follow-up
bug (see #4 below) was found in this same fix and corrected before it
shipped.

**Why it matters for a real payments system:** third-party placeholder
image services are an unreviewed external dependency with unpredictable
content — worth treating with the same scrutiny as any other unvetted
external input, especially anywhere a demo or production system displays
it publicly without a human reviewing every image first.

## 4. Duplicate placeholder thumbnails (follow-up to #3)

**What broke:** the category color palette used to generate the SVG
placeholders above (#3) only had 2 shades, but some products requested
3-4 gallery images — variants 1 and 3 (or 2 and 4) ended up pixel-identical,
which surfaced as a React "duplicate key" console warning, caught via a
live Playwright console-error check rather than assumed clean.

**The fix:** expanded each category's palette to 4 shades; also fixed the
underlying `key={url}` → `key={i}` in `ProductDetail.jsx`'s thumbnail
list as defense-in-depth, since a duplicate URL should never have been
able to collide as a React key in the first place.

**Why it matters:** console warnings are easy to treat as noise during a
demo build; this one was a real, user-visible defect (identical images
presented as if they were different angles of the product) that a
console-error check caught before a human happened to notice it visually.

---

## 5. The manual "Start Negotiation" button was still reachable after the automated flow shipped

**What broke:** once the cart-abandonment-triggered, voice-narrated
negotiation popup shipped (the actual intended UX), a leftover manual
"Start Negotiation" button remained on the product detail page and
catalog view — giving a shopper two different, inconsistent ways into the
same negotiation flow, one of which bypassed the intended trigger
entirely.

**The fix:** removed the manual button and its associated state/panel
usage from both `ProductDetail.jsx` and `CatalogView.jsx` — resolved
explicitly (via a direct question, not a silent guess) to remove it
**everywhere**, not just from the pages it was most obviously wrong on.

**Why it matters:** a leftover manual entry point into a flow that's
supposed to be automatically triggered is an easy way to end up with two
divergent code paths that quietly drift apart — exactly the shape of bug
that's cheap to fix immediately and expensive to untangle later.

---

## 6. Red-team-confirmed findings (Phase 11)

Two independent red-team suites were built and run live against this
system this project (`red-team-agent/`, an earlier narrative-report suite,
and `redteam/`, the newer structured five-category suite whose JSON
results are checked below). Between them, **five real gaps** were found
and fixed live, and **three remain open findings**, reported honestly
rather than silently absorbed into a passing scorecard.

### Fixed

- **Policy-gate `/verify` TOCTOU race (double-spend).** A read-then-write
  check on `Approval.used` let two concurrent redemptions of the same
  approval token both read `used=False` before either committed —
  reproduced live with real concurrent requests, both honoring the same
  negotiated discount on two separate Razorpay test-mode orders. Fixed
  with a single atomic `UPDATE ... WHERE used = 0` claim, checked by
  affected-row-count instead of a prior read. The identical anti-pattern
  in the backend's own `/agent/v1/pay` (`PurchaseIntent.used`) was
  hardened the same way pre-emptively.
- **Cross-buyer token theft (agent channel).** A buyer's approval_token
  had no concept of *who* it was issued to — any other authenticated
  buyer could redeem someone else's negotiated discount by presenting
  the token against their own checkout. Fixed by adding a `requester_id`
  column to policy-gate's `Approval` record, checked on redemption.
- **Cross-session token theft (human channel) — found by `redteam/`'s
  `tampering.py`.** The requester_id fix above deliberately never
  touched the human negotiation channel (no buyer identity exists
  there), which meant the *session*-scoping equivalent of the same gap
  was never actually closed for the one channel that has a
  caller-visible `session_id` at all. A token negotiated in one session
  was honored for a checkout claiming a completely different session's
  context. Fixed by adding an optional, opt-in `session_id` field to
  `OrderCreateRequest` and policy-gate's `VerifyRequest`, checked only
  when the caller supplies it (backward compatible) — and the real
  frontend checkout flow was updated to actually send it, not just the
  test harness.
- **Same-session negotiation race — found by extending the concurrency
  suite.** Two concurrent `POST /negotiate/message` calls for the *same*
  session both read the identical starting checkpoint and both advanced
  to the same turn, reproduced live as two responses reporting the
  identical `turn_count` — a browser double-click could have granted an
  extra, unearned discount-ladder rung. Fixed with a per-session
  `threading.Lock` around the read-state-then-resume sequence.
- **Webhook out-of-order status regression.** A stale/delayed
  `payment.failed` webhook arriving *after* the real `payment.captured`
  for the same order silently flipped a paid order's status back to
  `failed` — reproduced live with a real order. Fixed with a one-line
  guard: a `payment.failed` event no longer overwrites an
  already-`paid` order.

### Open findings (reported, not silently patched)

Checked directly against `redteam/results/*.json` at time of writing —
these are the only three non-PASS verdicts across all five categories:

- **`concurrency.same_session_double_negotiation`** — two concurrent
  `POST /negotiate/start` calls for the identical cart mint two fully
  independent, live negotiation sessions. Root cause: the endpoint has
  no caller-supplied cart/session identity field to de-duplicate on at
  all (only `product_id`/`cart_quantity`, which aren't unique — a
  shopper can legitimately open two separate negotiations for the same
  product on purpose). This is a real, if small, API contract gap (would
  need a new optional `cart_id` idempotency key), not a one-line database
  fix on the current schema — proposed but deliberately not applied, per
  that phase's own instruction to report real findings separately from
  fixing them.
- **`replay.webhook_replay`** — the webhook handler has no
  event_id/payment_id deduplication check at all. Harmless *today* only
  because every field it currently writes is a plain overwrite to an
  identical value, not an increment or a side-effecting action; the
  moment it does anything additive, a duplicate delivery (which
  Razorpay's own docs say to expect) would double-apply it.
- **`replay.stale_signature_replay`** — the webhook signature has no
  timestamp or nonce component at all, so a captured, validly-signed
  payload remains replayable indefinitely, not just within some short
  window after the original delivery.

---

## 7. An unconditional LLM call, found while red-teaming a different thing

**What broke:** Phase 11's x402 V2 conformance pass added an optional
conversational `message` field to `/agent/v1/negotiate`, with a
best-effort LLM call to generate a natural-language seller reply. That
call was implemented to run on *every* negotiate request, including
plain, non-conversational ones that never sent a `message` at all — which
meant every negotiate call paid an LLM round-trip whether it wanted a
chat reply or not. This surfaced as real read-timeouts once the red-team
suite started firing negotiate calls concurrently, hitting Groq's daily
quota and falling back to Gemini's own rate-limited tier under load.

**The fix:** the LLM framing call now only runs when the caller actually
sent its own `message` — a plain `proposed_terms`-only call is exactly as
fast as it was before that feature existed.

**Why it matters:** a feature that's "additive" in behavior can still be
non-additive in cost if it runs unconditionally — the actual regression
here wasn't in normal single-request testing, it only showed up under
concurrent load, which is exactly the kind of thing a red-team pass (built
for a different purpose entirely) is well-positioned to catch by accident.

---

## 8. Stale `proposed_offer` re-evaluated as fresh in the revenue-recovery simulator

**What broke:** `metrics/recovery_sim.py` (Phase 13) drives real
negotiation sessions and evaluates each new offer against a simulated
shopper's acceptance threshold. The negotiation graph can close a session
on its own judgment (the LLM deciding a further offer isn't worth making,
or the attempt cap) *without* producing a fresh offer that turn — in that
case, the API response still echoes the **previous** turn's
`proposed_offer` verbatim, since nothing overwrote it. The simulator's
first version checked `proposed_offer` before checking whether the
session had already `closed`, so it occasionally tried to send one more
message into an already-closed session — a clean 400 ("Negotiation
already closed"), surfacing as ~10-20% of simulated sessions erroring out
instead of resolving to a real conversion/non-conversion outcome.

**How it was found:** running a small test batch (n=5) before committing
to a full n=50 run, and reading the actual error body
(`{"detail": "Negotiation already closed"}`) instead of just the HTTP
status code — the status code alone doesn't distinguish "the harness has
a bug" from "the shopper legitimately walked away."

**The fix:** check `body.get("closed")` first, before ever looking at
`proposed_offer`, and treat a closed session as "no more offers, shopper
gave up" rather than re-evaluating a stale value as if it were new.

**Why it matters:** an API field that legitimately can hold a stale value
under one code path and a fresh one under another is a sharp edge for any
client, including a test harness — the safe read order is "check whether
this response even applies before trusting its contents," not the reverse.

---

## 9. Phase 17 trust-boundary tests: Policy Gate trusts a caller-supplied price with zero independent verification (CRITICAL)

**What broke:** `policy-gate/app/routes/evaluate.py`'s `POST /evaluate`
is a public HTTP endpoint (port 8001) with **no caller authentication**
and **no product catalog of its own**. It computes the discount floor —
`merchant_rules.min_allowed_unit_price(product_id, original_price)` —
entirely as a percentage of whatever `original_price` the *caller*
supplies in the request body. It never independently looks up what the
product actually costs. In the normal, unmodified application flow this
is invisible, because the only real caller is the backend itself, which
always supplies its own freshly-fetched `product.price`. But nothing
about the deployed system prevents calling Policy Gate's own public API
directly with a fabricated price.

**How it was found:** `tests/phase17_trust_boundary/test_17_3_price_tampering.py`,
written and run live against the actual running services as part of an
explicit adversarial test pass. Demonstrated end-to-end, twice, with real
requests against the real running services (not a mock, not a unit
test):

1. `POST http://127.0.0.1:8001/evaluate` directly, claiming
   `original_price=10000` (Rs 100.00) for product 1 (a Hand-Painted
   Ceramic Table Vase, which actually lists at `249900` = Rs 2,499.00),
   asking for a plausible-looking 10% off that fabricated number →
   **approved**, with a real, validly-signed `approval_token` issued.
2. That token redeemed through the real, completely unmodified
   `POST /order/create` checkout endpoint — the same one a real
   shopper's browser calls — produced a real Razorpay **test-mode**
   order for **Rs 90.00** (`order_TWHptwT7EIAtAE`) on a product actually
   worth **Rs 2,499.00**.

No internal code was called, no authentication was bypassed, no token
was forged — this is two public, documented endpoints, called in the
documented order, with one fabricated field in the first request.

**Status: reported, not yet fixed**, per this test phase's own
instruction to separate finding from fixing. The real fix is architectural,
not a one-line patch — Policy Gate needs either (a) its own read access to
authoritative product pricing (a synced/shared product table, or a
read-only call back to the backend's own `/product/{id}`, itself
requiring Policy Gate to stop trusting a client-supplied price
altogether), or (b) network-level lockdown so `/evaluate`/`/verify` are
only ever reachable from the backend's own process/network, never
publicly — and probably both, since "not publicly reachable today" is a
deployment fact, not a code guarantee.

**Why it matters for a real payments system:** this is the specific
failure mode the whole "separate, deterministic Policy Gate" architecture
exists to prevent — a merchant losing real revenue to a manipulated
discount — except it turns out the gate's own trust boundary has a hole
in the one input everything else depends on: what the item actually
costs. A service that is *itself* the authority on "was this discount
legitimate" cannot outsource "what was the original price" back to the
party asking for the discount.

## 10. Buyer agent's human-in-the-loop checkpoints have no timeout or session expiry

**What broke:** `buyer-agent/app/graph/nodes.py`'s
`await_negotiate_checkpoint` and `await_purchase_confirmation` both call
LangGraph's `interrupt()`, which halts execution until an explicit
`POST /shopper/chat` resumes it — there is no timer, no background sweep,
no "N seconds of silence" branch anywhere in this code. `MemorySaver`
(the checkpointer) holds a paused session in memory indefinitely.

**How it was found:** `tests/phase17_trust_boundary/test_17_4_checkpoint_no_autoproceed.py`
was written to test "does the agent abort on a timeout" as originally
specified — reading the actual graph code first (before writing the
test) showed that premise doesn't hold: there's no timeout concept to
trigger an abort. This is reported honestly rather than the test being
quietly rewritten to imply a timeout exists.

**Why this is NOT a security bug:** it actually makes the property that
matters *stronger* than a timeout-triggered abort would — there is no
code path at all from "human said nothing" to "purchase proceeds,"
verified live (waited 12s of total silence at both checkpoints, real
LLM-driven sessions, confirmed zero orders were created either time).

**Why it's still a real, open gap:** an abandoned session never expires,
consumes memory forever (worse under any sustained load — a script
opening many sessions and never replying would grow `MemorySaver`
without bound), and there is no "this session appears to have been
abandoned" signal anywhere for an operator to see. Not fixed as part of
this phase — reported per the same "find vs. fix" separation as #9.

## 11. Documentation/mental-model gap: the dashboard's tamper-detection sandbox is not actually isolated storage

**What was assumed (including in this phase's own test brief):** the
Merchant Dashboard's "try breaking the hash chain" sandbox demo operates
on a copy, snapshot, or in-memory structure separate from the real audit
trail.

**What's actually true**, traced in `backend/app/audit.py` and confirmed
live with an independent, out-of-band `sqlite3` connection bypassing the
API entirely: the sandbox chain (`session:demo:sandbox`) is written
through the exact same `write_audit_log()` function, into the exact same
`audit_logs` table, in the exact same production database file, as every
real negotiation and order event. There is no physical separation at
all. The isolation that actually holds is logical: each row's chain
membership is its own `chain_key`, and `verify_chain()` only ever walks
and links rows sharing one `chain_key` — so corrupting the sandbox's rows
can only ever break the sandbox's own hash linkage, never a real chain's,
even though they live in the same table. Verified live in
`test_17_6_sandbox_real_db_separation.py`: corrupted the sandbox,
confirmed its own verification broke, then independently re-verified the
real active chain and confirmed it was completely unaffected.

**Not a bug — a documentation correction.** Recorded here because acting
on the wrong mental model (e.g. "it's safe because it's a separate copy")
would have been the actual risk, not the sandbox's real (and correctly
functioning) isolation mechanism.

## 12. Phase 18 submission-readiness audit — the localhost/IPv6 bug was systemic, not isolated (FIXED)

**What broke:** the ~2-second `localhost`-vs-`127.0.0.1` latency bug first found and fixed on `backend`'s `POLICY_GATE_URL` (see the config file's own comment) turned out to be far more widespread than that one fix suggested. A genuine cold-start reproducibility audit — actually cloning the repo fresh and following only README.md — surfaced the SAME bug, unfixed, in nine more places: `buyer-agent/app/config.py`'s `SELLER_BASE_URL` (meaning every register/catalog/negotiate/purchase/pay call the buyer agent has ever made paid this tax), both frontend env files (wrong port too — `:8000`, three phases stale), `metrics/recovery_sim.py`, `analysis/simulate_revenue_impact.py`, both `demo/failure_beats/*.py` scripts, and both red-team suites' configs (`redteam/config.py`, `red-team-agent/app/config.py`) plus their `.env.example` files.

**How it was found:** the cold-start test wasn't just "does `pip install` work" — it measured real request timing with the exact tools each file actually uses (`requests` for the Python configs, `httpx` for `recovery_sim.py`, a real `fetch()` in Chromium for the frontend), rather than assuming the earlier fix generalized.

**The fix:** every instance above now defaults to `127.0.0.1`. This is now stated explicitly in README.md's own "Known Gotchas" section with the measured numbers, specifically so it doesn't get silently reintroduced a tenth time.

## 13. Phase 18 submission-readiness audit — almost no real payment in this project's history was ever actually confirmed as paid (FIXED, demo-critical)

**What broke:** this backend had exactly one path to `Order.status = "paid"` — a real Razorpay webhook delivery — which requires a public tunnel (`ngrok`) that has never actually been running in this project's local dev history. Checking the database directly: of 152 orders that existed at the time of this audit, only **9** had ever reached `"paid"` status, and every single one of those 9 was a `redteam` test script directly simulating a webhook call (`razorpay_payment_id` values like `pay_redteamreplay...`) to test replay/staleness protection — not a real payment completing through the normal user flow. The frontend's own checkout code had already been hedging around this: Razorpay's `handler` callback (which fires on a real successful payment) only ever set the status message to "Payment initiated," never "succeeded," and did nothing with the payment confirmation data Razorpay actually hands it.

**The practical consequence, unfixed:** a judge who completes a real Razorpay test-mode payment during a live demo would watch the Merchant Dashboard never reflect it — the order sits in `"created"` status forever, indistinguishable from one abandoned mid-checkout.

**How it was found:** exercising the human-error click-through this phase specifically asked for ("refresh mid-checkout") surfaced a related bug first (see #14), which prompted checking what `"created"`-vs-`"paid"` actually meant across the whole order history — not assumed from the code alone.

**The fix:** a new `POST /order/confirm` endpoint, called by the frontend the instant Razorpay's `handler` callback fires, independently verifying the payment via `razorpay_client.utility.verify_payment_signature` — the same HMAC mechanism Razorpay's own docs recommend for confirming a client-side checkout success without depending on a webhook, and consistent with this project's own standing rule that a client's claim is never trusted without independent verification. Confirmed live: a forged signature against a real order is correctly rejected (`400 Invalid payment signature`). A full browser-automated real-test-card walkthrough was attempted but Razorpay's real checkout iframe (several nested frames, ones Playwright couldn't reliably target within this pass) made full end-to-end UI automation impractical here — **a manual real-card walkthrough (`4111 1111 1111 1111`) is recommended before relying on this for a live demo**, though the verification mechanism itself was tested directly and is standard, well-documented Razorpay behavior.

## 14. Phase 18 submission-readiness audit — abandoned/unpaid orders inflated the dashboard's revenue numbers (FIXED)

**What broke:** `dashboard_summary()`'s revenue calculation filtered orders by `status != "failed"` — which includes `"created"` (an order row that exists because `/order/create` ran, but no payment was ever completed). Reproduced live as part of the "refresh mid-checkout" human-error path: creating an order and never paying it moved `total_revenue` from ₹200,986.04 to ₹202,885.04 — the full product price counted as real revenue for a payment that never happened. Combined with finding #13 above, this meant the dashboard's headline revenue figure was built almost entirely from orders that were never actually confirmed paid.

**The fix:** the revenue/channel-breakdown calculation now filters to `status == "paid"` specifically. `total_orders` and `orders_by_status` deliberately still count every attempt, including abandoned ones — that's a legitimate funnel view — only *revenue* changed to mean "money actually collected."

## 15. Phase 18 submission-readiness audit — a fast double-click fired two real orders (FIXED)

**What broke:** neither `ProductDetail.jsx`'s "Buy Now" nor `CatalogView.jsx`'s (admin) "Buy" button guarded against a second click firing while the first `POST /order/create` call was still in flight. Reproduced live with a scripted rapid double-click: two separate `/order/create` calls, 26ms apart, two separate real Razorpay orders for one click's worth of intent. `Cart.jsx`'s own checkout button already had this guard (`checkingOut` state) — the other two call sites just hadn't been given the same treatment.

**The fix:** both buttons now track their own in-flight state (`checkingOut` / `checkingOutId`, the latter keyed per-product since `CatalogView` renders one button per row) and become a no-op — not just visually disabled, actually guarded in the handler itself — while a checkout is already in progress. Verified live: the same double-click script now produces exactly one `/order/create` call.

## 16. Phase 18 audit note — an unfixed documentation/reality gap: only one commit exists in git history

**What was found:** at the time of this audit, `git log` showed exactly one commit ("Phase 1: foundation"), with 24 modified and 50 untracked files/directories — meaning `buyer-agent/`, both red-team suites, `metrics/`, `docs/`, `demo/`, and the entire `tests/phase17_trust_boundary/` suite were not in version control at all. A real `git clone` of this repository's `origin` remote would retrieve only Phase 1.

**Status: flagged, not resolved by this audit.** Committing and pushing 15+ phases of work is a deliberate, visible action on a shared remote — outside what this audit performed on its own judgment. See `RUBRIC_MAPPING.md` for why this matters beyond reproducibility (a "development process" judging criterion, if one exists, cannot be assessed from a single squashed commit).

---

## A note on what this list is for

Every item above changed something real: a fix landed in the running
code, a design decision got made explicitly instead of by default, or a
finding got written down as still-open rather than quietly ignored. The
three open red-team findings, the two open Phase 17 findings (#9 is
the most serious thing in this entire document — read it if you read
nothing else here), and Phase 18's one open item (#16, git history) are
not embarrassing — they're the honest edge of what a real, timeboxed build covers, stated plainly enough that the next
person to pick this up knows exactly where to start.
