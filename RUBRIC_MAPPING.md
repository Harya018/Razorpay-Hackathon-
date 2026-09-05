# Rubric Mapping — Track 1

## ⚠️ Source status: the actual published Track 1 judging criteria were not available when this document was written

This document was requested as part of a submission-readiness audit
(Phase 18). Per that phase's own instruction — "flag this explicitly
rather than guessing at criteria" — that's exactly what this is: **the
mapping below uses commonly-published hackathon judging categories as a
labeled placeholder structure, not the actual Track 1 rubric.** Do not
submit this as-is if the real criteria differ in wording, weighting, or
category count.

**To finish this document properly:** paste the actual Track 1 judging
criteria (from the event page, submission portal, or organizer email)
and this table gets rebuilt against the real wording, in the real order,
with the real weighting if published.

---

## Placeholder mapping (generic hackathon criteria)

| Criterion (generic) | Addressed? | Where / how |
|---|---|---|
| **Technical execution / functionality** | Strong | Four independently deployable services (`backend`, `policy-gate`, `buyer-agent`, `frontend`), real Razorpay test-mode payments, real LLM negotiation (Groq, with a Gemini fallback tier), a hash-chained tamper-evident audit log, and six adversarial pytest suites (`tests/phase17_trust_boundary/`) run live against the running system — not just unit tests. |
| **Innovation / originality** | Moderate-to-strong, not independently benchmarked | The core idea — an LLM that frames a negotiation but a separate, deterministic, zero-LLM Policy Gate that is the sole authority on whether a discount is real — is the project's actual thesis, not a bolt-on feature. No claim is made here about how this compares to other teams' approaches, since that's inherently unknowable in advance. |
| **Real-world impact / usefulness** | Address, with an honest caveat | The revenue-recovery framing (negotiation recovers abandoned carts) is directly business-relevant, but the headline recovery-rate number is **simulated**, not measured against real shoppers — see the methodology note directly on the Merchant Dashboard's "Revenue Recovery (Simulated)" card, and the Sales Analytics page's real (non-simulated) negotiation funnel and discount-tier numbers for what's actually measured. |
| **Security / robustness** | Strong — zero open critical findings | Two independent red-team suites (`redteam/`, `red-team-agent/`) plus the Phase 17 trust-boundary suite were run live against the system, not claimed from code review. Six real gaps were found and fixed pre-submission (see `WHAT_BROKE.md`), including the one critical finding: Policy Gate's `/evaluate` used to trust a caller-supplied price with no independent re-validation — a live, demonstrated exploit chain (`WHAT_BROKE.md` §9) that bought a ₹2,499 product for ₹90 by lying to a public endpoint. Fixed in Phase 20 (Policy Gate now cross-checks every price against the backend's real catalog, fails closed if it can't) and closed by re-running the exact exploit test against the patched system, not just reviewing the diff. Three smaller, lower-severity red-team findings remain open and are reported as such (concurrency dedup on `/negotiate/start`, webhook replay dedup, stale-signature replay window) — see `WHAT_BROKE.md` §6. |
| **Presentation / demo quality** | Addressed | Two visually distinct, deliberately different design registers (a warm handmade-craft storefront vs. a slate/mono "audit-grade instrument panel" dashboard), a live hash-chain tamper-detection demo a judge can trigger themselves, and a documented fallback mechanism (§18.5, `demo/`) for third-party (Groq/Razorpay) flakiness during a live demo. |
| **Completeness / polish** | Addressed, with known gaps stated plainly | `WHAT_BROKE.md` documents every real bug found across the build — including ones still open — rather than presenting a scorecard with no visible seams. A cold-start reproducibility audit (Phase 18.1) found and fixed real setup-documentation gaps before submission rather than assuming the README was accurate. |
| **Team process / use of time** | Not independently verifiable from the repo alone | Commit history currently reflects one squashed "Phase 1: foundation" commit, with all subsequent phases uncommitted at the time of this audit (see the Phase 18 cold-start findings) — if judged on commit-by-commit process, this needs to be resolved (regular commits pushed to `origin`) before submission, independent of code quality. |

## Explicitly flagged weak spots (not omitted)

- **Real-world impact's headline number is simulated**, not measured — stated plainly on the number itself now (§18.3), but a skeptical judge asking "is this real?" should get "no, and here's exactly what it assumes" as the honest answer, every time.
- **One critical, unfixed security finding** (Policy Gate price-tampering, `WHAT_BROKE.md` §9) — reported as an open item because it was found via genuine adversarial testing against the live system, not a hypothetical.
- **Git history does not reflect the actual development process** — a single commit covers only the earliest phase; everything since is uncommitted as of this audit. Worth fixing before a judge (or a "check their commit history" criterion) looks.
