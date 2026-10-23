#!/usr/bin/env python3
"""Validate dataset and rubric files against the schemas in CLAUDE.md. Exit 1 on any problem."""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPICS = {"installation", "locators", "assertions", "actions", "auth", "network", "fixtures", "config",
          "test-runner", "debugging", "reporting", "ci", "api-testing", "browsers", "visual-testing", "mobile-emulation"}
SPECS = {
    "golden": ("g", {"question": str, "expected_answer": str, "source_url": str, "topic": str, "difficulty": str}),
    "adversarial": ("a", {"category": str, "prompt": str, "expected_behavior": str, "must_not_contain": list, "severity": str}),
    "unanswerable": ("u", {"category": str, "question": str, "expected_behavior": str, "must_not_contain": list}),
}
ENUMS = {
    ("golden", "topic"): TOPICS, ("golden", "difficulty"): {"easy", "medium", "hard"},
    ("adversarial", "category"): {"jailbreak", "prompt_injection", "off_topic"},
    ("adversarial", "severity"): {"low", "medium", "high", "critical"},
    ("unanswerable", "category"): {"nonexistent_api", "out_of_scope", "false_premise"},
}


def check_file(name, errs):
    prefix, fields = SPECS[name]
    path = ROOT / "data" / f"{name}.jsonl"
    seen = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if not line:
            if n != len(path.read_text(encoding="utf-8").split("\n")):
                errs.append(f"{path.name}:{n}: blank line")
            continue
        try:
            row = json.loads(line)
        except ValueError as e:
            errs.append(f"{path.name}:{n}: invalid JSON ({e})"); continue
        rid = row.get("id", "")
        if not re.fullmatch(prefix + r"\d{3}", str(rid)):
            errs.append(f"{path.name}:{n}: bad id {rid!r}")
        if rid in seen:
            errs.append(f"{path.name}:{n}: duplicate id {rid}")
        seen.add(rid)
        for f, t in fields.items():
            if not isinstance(row.get(f), t) or row.get(f) in ("", None):
                if not (t is list and row.get(f) == []):
                    errs.append(f"{path.name}:{n}: {rid} missing/invalid {f}")
        for (nm, f), allowed in ENUMS.items():
            if nm == name and row.get(f) not in allowed:
                errs.append(f"{path.name}:{n}: {rid} {f}={row.get(f)!r} not allowed")
        if name == "golden" and not str(row.get("source_url", "")).startswith("https://playwright.dev/docs/"):
            errs.append(f"{path.name}:{n}: {rid} source_url not a playwright.dev docs URL")
        if name == "adversarial" and not row.get("must_not_contain") and not row.get("expected_behavior"):
            errs.append(f"{path.name}:{n}: {rid} has no check")
        if name == "unanswerable":
            for k in ("source_url", "reference_fact"):
                if k not in row:
                    errs.append(f"{path.name}:{n}: {rid} missing {k}")
            if row.get("category") == "false_premise" and not row.get("reference_fact"):
                errs.append(f"{path.name}:{n}: {rid} false_premise needs reference_fact")
    return len(seen)


def main():
    errs = []
    for name in SPECS:
        print(f"{name}: {check_file(name, errs)} cases")
    for p in sorted((ROOT / "rubrics").glob("*.json")) + [ROOT / "gate.json"]:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if p.parent.name == "rubrics" and "version" not in d:
                errs.append(f"{p.name}: missing version")
        except ValueError as e:
            errs.append(f"{p.name}: invalid JSON ({e})")
    for e in errs:
        print("ERROR", e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
