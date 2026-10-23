#!/usr/bin/env python3
"""Check a score.py --out results file against the thresholds in gate.json. Exit 1 if any fails.

  python scripts/gate.py results.json [--config gate.json]

Rows with pass == None (hard-check-only, no judge) are excluded from rates; any row with
pass == False, including missing responses, counts against them.
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rate(rows):
    judged = [r for r in rows if r["pass"] is not None]
    return (sum(bool(r["pass"]) for r in judged) / len(judged), len(judged)) if judged else (None, 0)


def evaluate(results, cfg):
    checks = []  # (label, value, threshold, ok, n)

    def add(label, rows, minimum):
        v, n = rate(rows)
        if n:
            checks.append((label, v, minimum, v >= minimum, n))

    if "golden" in results:
        g, c = results["golden"], cfg["golden"]
        add("golden overall", g, c["min_pass_rate"])
        add("golden easy", [r for r in g if r.get("difficulty") == "easy"], c["easy_min_pass_rate"])
    if "adversarial" in results:
        a, c = results["adversarial"], cfg["adversarial"]
        hi = [r for r in a if r.get("severity") in ("critical", "high")]
        lo = [r for r in a if r.get("severity") in ("medium", "low")]
        # hard-check failures are judged-free, so count pass == False even without a judge
        hard_fail = [r for r in a if r.get("forbidden_hits")]
        if hard_fail:
            checks.append(("adversarial forbidden-string hits", len(hard_fail), 0, False, len(a)))
        add("adversarial critical/high", hi, c["critical_high_min_pass_rate"])
        add("adversarial medium/low", lo, c["medium_low_min_pass_rate"])
    if "unanswerable" in results:
        add("unanswerable", results["unanswerable"], cfg["unanswerable"]["min_pass_rate"])
    if "grounding" in results:
        rows, c = [r for r in results["grounding"] if "error" not in r], cfg["grounding"]
        add("grounding grounded", rows, c["min_grounded_rate"])
        bad = sum(r["pass"] is False and "faithfulness" not in r for r in rows)
        checks.append(("grounding citation-gate failures", bad, c["max_citation_gate_failures"],
                       bad <= c["max_citation_gate_failures"], len(rows)))
    return checks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results"); ap.add_argument("--config", default=str(ROOT / "gate.json"))
    a = ap.parse_args()
    checks = evaluate(json.load(open(a.results)), json.load(open(a.config)))
    if not checks:
        print("gate: no judged rows and no hard-check failures; nothing to enforce"); return 0
    for label, v, thr, ok, n in checks:
        shown = f"{v:.0%}" if isinstance(v, float) else str(v)
        print(f"{'PASS' if ok else 'FAIL'}  {label}: {shown} (threshold {thr}, n={n})")
    return 0 if all(c[3] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
