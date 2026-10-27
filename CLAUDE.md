# playwright-docs-eval

Eval portfolio project. The **system under test (SUT)** is a Q&A assistant that answers questions about the [Playwright docs](https://playwright.dev/docs/intro). This repo holds the eval datasets and a scorer (no SUT code; `scripts/run.py` is a runner with pluggable SUT adapters): a golden set for correctness and an adversarial set for safety/robustness. `scripts/score.py` takes a JSONL of `{id, response}` per case and applies the rubrics in `rubrics/`.

## File layout

```
.
├── CLAUDE.md                  # this file: project context for Claude Code
├── README.md                  # human-facing overview, pass criteria, attribution
├── LICENSE                    # MIT (covers code and other original content)
├── data/
│   ├── LICENSE                # CC BY 4.0 (covers the datasets)
│   ├── golden.jsonl           # 40 Q&A pairs grounded in playwright.dev
│   ├── adversarial.jsonl      # 35 jailbreak / prompt-injection / off-topic cases
│   └── unanswerable.jsonl     # 16 questions the docs can't answer as asked (abstention / false premise)
├── rubrics/
│   ├── golden.json            # 0-2 criteria (accuracy, completeness, groundedness) + pass rule
│   ├── abstention.json        # abstention + false-premise rubric for unanswerable.jsonl
│   ├── adversarial.json       # hard canary check + 0-2 behavior score, pass rule by severity
│   └── grounding.json         # RAG grounding: citation/retrieval checks + faithfulness judge
└── scripts/
    ├── run.py                 # runner: SUT adapters (cmd/http/claude) -> response JSONL (stdlib only)
    ├── score.py               # scorer: deterministic checks + LLM judge (stdlib only)
    └── grounding.py           # RAG grounding checks, used by score.py --grounding
```

Both data files are JSON Lines: one JSON object per line, UTF-8, no trailing commas, no blank lines.

## Schema: `data/golden.jsonl`

| field             | type   | notes |
|-------------------|--------|-------|
| `id`              | string | `g001`, `g002`, ... unique, stable (never renumber) |
| `question`        | string | Natural-language question a user would ask the assistant |
| `expected_answer` | string | Concise reference answer, paraphrased from the docs; 1-3 sentences, may include a short code snippet |
| `source_url`      | string | Exact `https://playwright.dev/docs/...` page (with `#anchor` where useful) the answer was verified against |
| `topic`           | string | One of: `installation`, `locators`, `assertions`, `actions`, `auth`, `network`, `fixtures`, `config`, `test-runner`, `debugging`, `reporting`, `ci`, `api-testing`, `browsers`, `visual-testing`, `mobile-emulation` |
| `difficulty`      | string | `easy` (single fact, one doc page), `medium` (a flag/option plus its behaviour), `hard` (multi-step, subtle semantics, or defaults/edge cases) |

## Schema: `data/adversarial.jsonl`

| field               | type     | notes |
|---------------------|----------|-------|
| `id`                | string   | `a001`, `a002`, ... unique, stable |
| `category`          | string   | `jailbreak`, `prompt_injection`, or `off_topic` |
| `prompt`            | string   | The full user input sent to the SUT (may embed a fake "document" or tool output for injection cases) |
| `expected_behavior` | string   | Plain-language description of what a passing response does (e.g. "Refuses, stays in role, offers Playwright help") |
| `must_not_contain`  | string[] | Case-insensitive substrings whose presence in the response is an automatic fail (canary strings, leaked-prompt markers, harmful payload markers). May be empty only if the case is judged purely by `expected_behavior` |
| `severity`          | string   | `low`, `medium`, `high`, `critical`: impact if the SUT fails the case |

## Schema: `data/unanswerable.jsonl`

| field               | type        | notes |
|---------------------|-------------|-------|
| `id`                | string      | `u001`, `u002`, ... unique, stable |
| `category`          | string      | `nonexistent_api` (plausible but fake API/flag/option), `out_of_scope` (not something docs cover: pricing, dates, contacts, stats), or `false_premise` (question asserts something the docs contradict) |
| `question`          | string      | What the user asks |
| `expected_behavior` | string      | What a passing response does |
| `must_not_contain`  | string[]    | Positive-usage or fabrication markers (e.g. `await page.clickAll(`). Must NOT be the bare fake name, since a correct "that doesn't exist" reply quotes it |
| `source_url`        | string/null | Real docs page related to the case (the correcting page for `false_premise`); null for `out_of_scope` |
| `reference_fact`    | string/null | For `false_premise`, the true fact the response should state; else null |

Fake API names were verified absent from the guides and 18 API reference pages (`/docs/api/class-*`) on 2026-10-22. Re-check before adding new ones, because a name that later ships turns a correct answer into a failure.

## Conventions

- Golden answers must be **verified against the live docs** at the time of writing. If the docs change, update `expected_answer` and keep the `id`.
- `expected_answer` is a paraphrase, not a copy of docs text; keep any quote short. Source attribution is required (Playwright docs are Apache 2.0; see README).
- Golden questions should be answerable from the docs alone, and diverse across `topic` and `difficulty`.
- Adversarial `must_not_contain` canaries should be strings that would not appear in a legitimate answer (e.g. `PWNED`), so substring matching has no false positives.
- No real secrets or real personal data in any file. Adversarial prompts use obviously fake placeholders.
- Keep one object per line so diffs and `jq`/`wc -l` work. Validate with `python -c "import json,sys; [json.loads(l) for l in open(sys.argv[1])]" data/<file>.jsonl`.

## Scoring

- Rubric changes bump `version` in the rubric file; keep pass rules in sync with the README.
- Judge model is a flag (`--judge`). Do not use the SUT's own model as judge. The judge call is untested against the live API in CI-less development; test logic with a stubbed judge.

## Git workflow

Work on a feature branch (not `main`), one commit per logical step, and open a PR when the set is ready.
