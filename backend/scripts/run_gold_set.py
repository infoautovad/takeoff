"""Run gold-set takeoff comparisons and print a miss matrix.

Usage (from backend/):
  python scripts/run_gold_set.py
  python scripts/run_gold_set.py --case sample_utility
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.eoq_eval import compare_eoq, summarize_report  # noqa: E402
from app.services.cad.quantity_engine import build_quantities  # noqa: E402

GOLD_ROOT = ROOT / "tests" / "gold_set" / "cases"


def run_case(case_dir: Path) -> dict:
    expected = json.loads((case_dir / "expected_eoq.json").read_text(encoding="utf-8"))
    extraction_path = case_dir / "extraction.json"
    actual_path = case_dir / "actual_eoq.json"

    if extraction_path.exists():
        extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
        actual = build_quantities(extraction, source_label=case_dir.name)
    elif actual_path.exists():
        actual = json.loads(actual_path.read_text(encoding="utf-8"))
        if isinstance(actual, dict):
            actual = actual.get("items") or []
    else:
        raise FileNotFoundError(f"{case_dir}: need extraction.json or actual_eoq.json")

    report = compare_eoq(expected, actual)
    return {
        "case": expected.get("id") or case_dir.name,
        "name": expected.get("name") or case_dir.name,
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AutoVAD gold-set EOQ comparisons")
    parser.add_argument("--case", help="Run a single case id (folder name)")
    parser.add_argument("--json", action="store_true", help="Emit JSON reports")
    args = parser.parse_args()

    cases = sorted(p for p in GOLD_ROOT.iterdir() if p.is_dir())
    if args.case:
        cases = [GOLD_ROOT / args.case]
        if not cases[0].exists():
            print(f"Unknown case: {args.case}", file=sys.stderr)
            return 2

    failed = 0
    print(f"Gold-set root: {GOLD_ROOT}\n")
    for case_dir in cases:
        result = run_case(case_dir)
        report = result["report"]
        print("=" * 60)
        print(f"CASE: {result['case']} — {result['name']}")
        print(summarize_report(report))
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        if report.misses or report.qty_errors or report.recall < 0.85:
            failed += 1

    print("=" * 60)
    print(
        f"Done. {len(cases) - failed}/{len(cases)} cases passed "
        "(recall>=85%, no misses/qty errors)."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
