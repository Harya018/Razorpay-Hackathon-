"""Stable result schema + JSON writer shared across every scenario module
in this suite (concurrency.py now; replay/injection/tampering/trust
later). One row per attack scenario, one file per category —
redteam/results/{category}_results.json.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

Verdict = Literal["PASS", "FAIL"]


@dataclass
class AttackResult:
    attack_id: str
    description: str
    requests_sent: int
    expected_successes: int
    actual_successes: int
    blocked: bool  # True if the attack's intended bypass was actually blocked
    verdict: Verdict
    notes: str = ""
    # Injection-scenario-only fields (11c) — left None for every other
    # category, never fabricated where they don't apply. Two SEPARATE
    # signals on purpose: llm_confused is a best-effort text heuristic on
    # the agent's own reply (approximate, never used to decide verdict);
    # policy_bypassed is checked against the actual audit trail of what
    # the policy gate approved, and IS what decides the verdict. An agent
    # that sounds rattled but never causes an unauthorized gate approval
    # is a PASS — "did the LLM get confused" and "did it matter" are
    # different findings, and only the second one protects the merchant.
    llm_confused: Optional[bool] = None
    policy_bypassed: Optional[bool] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "attack_id": self.attack_id,
            "description": self.description,
            "requests_sent": self.requests_sent,
            "expected_successes": self.expected_successes,
            "actual_successes": self.actual_successes,
            "blocked": self.blocked,
            "verdict": self.verdict,
            "notes": self.notes,
            "llm_confused": self.llm_confused,
            "policy_bypassed": self.policy_bypassed,
            "timestamp": self.timestamp,
        }


def write_results(category: str, results: list[AttackResult], results_dir: str = "results") -> str:
    out_dir = Path(__file__).parent / results_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{category}_results.json"
    out_path.write_text(
        json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return str(out_path)
