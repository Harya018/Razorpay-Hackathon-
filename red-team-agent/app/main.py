import argparse
import sys

from app.attacks import (
    audit_tamper_attempt,
    concurrent_race,
    malformed_terms,
    parameter_tampering,
    prompt_injection,
    token_replay_variants,
    trust_boundary,
    webhook_replay,
)
from app.report import write_report, write_category_json

ATTACKS = {
    "prompt_injection": prompt_injection.run,
    "malformed_terms": malformed_terms.run,
    "concurrent_race": concurrent_race.run,
    "token_replay_variants": token_replay_variants.run,
    "audit_tamper_attempt": audit_tamper_attempt.run,
    "webhook_replay": webhook_replay.run,
    "parameter_tampering": parameter_tampering.run,
    "trust_boundary": trust_boundary.run,
}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Adversarial red-team agent against the seller's own backend")
    parser.add_argument(
        "attack", nargs="?", default="--all",
        help=f"One of: {', '.join(ATTACKS)}, or 'all' to run every attack and write the full report",
    )
    parser.add_argument("--out", default="results/red_team_report.md", help="Report output path (only used with 'all')")
    args = parser.parse_args()

    if args.attack in ("--all", "all"):
        results = []
        for name, fn in ATTACKS.items():
            print(f"\n=== Running {name} ===")
            module_result = fn()
            results.append(module_result)
            for case in module_result.cases:
                print(f"  [{case.verdict}] {case.name}")

        write_report(results, args.out)
        written = write_category_json(results, "results")
        for category, path in written.items():
            print(f"  wrote {path}")

        total = sum(len(r.cases) for r in results)
        failed = sum(1 for r in results for c in r.cases if c.verdict == "FAIL")
        print(f"\n=== SUMMARY: {total - failed}/{total} passed, {failed} failed ===")
        print(f"Full report written to {args.out}")
        sys.exit(1 if failed else 0)

    if args.attack not in ATTACKS:
        print(f"Unknown attack '{args.attack}'. Choose from: {', '.join(ATTACKS)}, or 'all'.")
        sys.exit(2)

    module_result = ATTACKS[args.attack]()
    for case in module_result.cases:
        print(f"\n[{case.verdict}] {case.name}")
        print(f"  {case.notes}")
    failed = any(c.verdict == "FAIL" for c in module_result.cases)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
