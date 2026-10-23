import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import gate, score

CFG = json.load(open(ROOT / "gate.json"))


def failed(results):
    return [c[0] for c in gate.evaluate(results, CFG) if not c[3]]


class GateTests(unittest.TestCase):
    def test_golden_pass_and_fail(self):
        rows = [{"pass": True, "difficulty": "easy"}] * 9 + [{"pass": True, "difficulty": "hard"}]
        self.assertEqual(failed({"golden": rows}), [])
        self.assertIn("golden easy", failed({"golden": rows + [{"pass": False, "difficulty": "easy"}]}))

    def test_adversarial_severity_split(self):
        ok = [{"pass": True, "severity": "critical"}, {"pass": True, "severity": "low"}]
        self.assertEqual(failed({"adversarial": ok}), [])
        self.assertIn("adversarial critical/high",
                      failed({"adversarial": ok + [{"pass": False, "severity": "high"}]}))

    def test_forbidden_hit_fails_even_without_judge(self):
        rows = [{"pass": False, "severity": "low", "forbidden_hits": ["PWNED"]}]
        self.assertIn("adversarial forbidden-string hits", failed({"adversarial": rows}))

    def test_unjudged_rows_ignored(self):
        self.assertEqual(gate.evaluate({"golden": [{"pass": None, "difficulty": "easy"}]}, CFG), [])

    def test_grounding_citation_gate(self):
        rows = [{"pass": False}, {"pass": True, "faithfulness": 2}]
        self.assertIn("grounding citation-gate failures", failed({"grounding": rows}))

    def test_scorer_with_stub_judge(self):
        cases = score.load(ROOT / "data/golden.jsonl")[:2]
        rub = json.load(open(ROOT / "rubrics/golden.json"))
        stub = lambda p: '{"accuracy": 2, "completeness": 2, "groundedness": 2, "reason": "ok"}'
        rows = score.score_golden(cases, {c["id"]: "x" for c in cases}, rub, stub)
        self.assertTrue(all(r["pass"] for r in rows))

    def test_validate_data_clean(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts/validate_data.py")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
