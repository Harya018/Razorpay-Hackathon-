"""Shared result type + Markdown report writer for every attack module."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

Verdict = Literal["PASS", "FAIL", "PASS_CONFIRMS_DOCUMENTED_LIMITATION"]


@dataclass
class AttackCase:
    """One individual, checkable attempt within an attack module (a module
    may run several — e.g. token_replay_variants.py has three distinct
    sub-cases).
    """

    name: str
    description: str
    request: str  # the exact request/payload used, as a human-readable string (curl-ish or JSON)
    actual_response: str  # what the system actually did, verbatim enough to be checked
    verdict: Verdict
    notes: str = ""
    fix_applied: Optional[str] = None  # filled in only if a FAIL was found and then fixed
    # Dashboard-scorecard fields (added for the "Security Posture" panel).
    # All optional — most cases are pass/fail checks with no meaningful
    # request count, so these are only populated where they mean something
    # (concurrency/replay cases set requests_sent/expected/actual;
    # injection cases set llm_confused/policy_bypassed instead). Never
    # invented where they don't apply — an absent field in the JSON output
    # is more honest than a fabricated 1/1.
    requests_sent: Optional[int] = None
    expected_successes: Optional[int] = None
    actual_successes: Optional[int] = None
    blocked: Optional[bool] = None  # True if the attack's intended bypass was blocked, False if it got through
    llm_confused: Optional[bool] = None  # injection cases only — did the LLM's text comply/waver
    policy_bypassed: Optional[bool] = None  # injection cases only — did an actual gate-bound action result


@dataclass
class AttackModuleResult:
    module: str
    # Dashboard category this module rolls up into — one of concurrency,
    # replay, injection, tampering, trust_boundary. Drives the per-category
    # breakdown on the merchant dashboard's Security Posture panel.
    category: str = "uncategorized"
    cases: list[AttackCase] = field(default_factory=list)

    def add(self, case: AttackCase) -> None:
        self.cases.append(case)

    @property
    def any_fail(self) -> bool:
        return any(c.verdict == "FAIL" for c in self.cases)


def _verdict_badge(v: Verdict) -> str:
    return {
        "PASS": "✅ PASS",
        "FAIL": "❌ FAIL",
        "PASS_CONFIRMS_DOCUMENTED_LIMITATION": "⚠️ PASS (confirms already-documented limitation)",
    }[v]


def write_report(results: list[AttackModuleResult], out_path: str) -> None:
    total_cases = sum(len(r.cases) for r in results)
    total_fail = sum(1 for r in results for c in r.cases if c.verdict == "FAIL")
    total_pass = total_cases - total_fail
    fixed_cases = [(r.module, c) for r in results for c in r.cases if c.fix_applied]

    lines = []
    lines.append("# Red-Team Report — Phase 8 Part B")
    lines.append("")
    lines.append(f"Generated {datetime.now(timezone.utc).isoformat()} against a live, running instance of")
    lines.append("`/backend`, `/policy-gate`, and the merchant's Razorpay test-mode account.")
    lines.append("Every request below was actually sent over HTTP (or, where explicitly noted, direct")
    lines.append("SQLite writes bypassing the application layer entirely) — nothing here is simulated.")
    lines.append("")
    lines.append(f"**Summary: {total_pass}/{total_cases} cases passed, {total_fail} failed, on THIS run.**")
    if fixed_cases:
        lines.append("")
        lines.append(
            f"**Read this before the zero above reassures you: {len(fixed_cases)} real gap(s) WERE found during "
            f"this red-team exercise, on an earlier run, and are the reason this run is clean — they were fixed "
            f"in between, and this run is the re-verification.** A 0-failure run on its own proves nothing; it's "
            f"only meaningful together with the record of what was found and fixed to get here. Skip straight to "
            f"the \"Fix applied\" sections below for the full original-failure → root-cause → fix → re-verification "
            f"account of each:"
        )
        for module, case in fixed_cases:
            lines.append(f"- `{module}` → **{case.name}**")
    elif total_fail == 0:
        lines.append("")
        lines.append(
            "No attack found a gap this run, and none were found and fixed earlier in this exercise either. See "
            "each module below for exactly what was tried — a zero-failure report is only as credible as the "
            "attacks it ran; the point of this report is to let you judge that for yourself, not to take the zero "
            "on faith."
        )
    lines.append("")
    lines.append("| # | Module | Case | Verdict |")
    lines.append("|---|---|---|---|")
    i = 0
    for r in results:
        for c in r.cases:
            i += 1
            lines.append(f"| {i} | `{r.module}` | {c.name} | {_verdict_badge(c.verdict)} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    for r in results:
        lines.append(f"## `{r.module}`")
        lines.append("")
        for c in r.cases:
            lines.append(f"### {c.name} — {_verdict_badge(c.verdict)}")
            lines.append("")
            lines.append(c.description)
            lines.append("")
            lines.append("**Request/payload used:**")
            lines.append("```")
            lines.append(c.request.strip())
            lines.append("```")
            lines.append("")
            lines.append("**System's actual response:**")
            lines.append("```")
            lines.append(c.actual_response.strip())
            lines.append("```")
            lines.append("")
            if c.notes:
                lines.append(f"**Notes:** {c.notes}")
                lines.append("")
            if c.fix_applied:
                lines.append(f"**Fix applied:** {c.fix_applied}")
                lines.append("")
        lines.append("---")
        lines.append("")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def to_json_summary(results: list[AttackModuleResult]) -> str:
    return json.dumps(
        [
            {
                "module": r.module,
                "cases": [
                    {"name": c.name, "verdict": c.verdict, "notes": c.notes}
                    for c in r.cases
                ],
            }
            for r in results
        ],
        indent=2,
    )


CATEGORY_RESULT_FILES = {
    "concurrency": "concurrency_results.json",
    "replay": "replay_results.json",
    "injection": "injection_results.json",
    "tampering": "tampering_results.json",
    "trust_boundary": "trust_results.json",
}


def write_category_json(results: list[AttackModuleResult], out_dir: str) -> dict[str, str]:
    """Groups every case by its module's `category` and writes one JSON
    file per category into out_dir, in the shared scorecard schema:
    attack_id, description, requests_sent, expected_successes,
    actual_successes, blocked, verdict, timestamp. This is what the
    merchant dashboard's Security Posture panel reads — never the
    Markdown report, which is for humans.

    Returns {category: written_path} for whichever categories actually had
    at least one case this run (a category with zero cases writes nothing,
    rather than an empty/misleading file).
    """
    now = datetime.now(timezone.utc).isoformat()
    by_category: dict[str, list[dict]] = {}
    for r in results:
        filename = CATEGORY_RESULT_FILES.get(r.category)
        if filename is None:
            continue  # uncategorized modules don't feed the dashboard
        entries = by_category.setdefault(r.category, [])
        for i, c in enumerate(r.cases):
            entries.append(
                {
                    "attack_id": f"{r.module}.{i}",
                    "module": r.module,
                    "name": c.name,
                    "description": c.description,
                    "requests_sent": c.requests_sent,
                    "expected_successes": c.expected_successes,
                    "actual_successes": c.actual_successes,
                    "blocked": c.blocked,
                    "llm_confused": c.llm_confused,
                    "policy_bypassed": c.policy_bypassed,
                    "verdict": c.verdict,
                    "notes": c.notes,
                    "timestamp": now,
                }
            )

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    written = {}
    for category, entries in by_category.items():
        filename = CATEGORY_RESULT_FILES[category]
        full_path = out_path / filename
        full_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        written[category] = str(full_path)
    return written
