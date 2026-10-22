# playwright-docs-eval

Eval portfolio project. The **system under test (SUT)** is a Q&A assistant that answers questions about the [Playwright docs](https://playwright.dev/docs/intro). This repo holds the eval datasets only (no SUT code, no runner yet): a golden set for correctness and an adversarial set for safety/robustness.

## File layout

```
.
├── CLAUDE.md                  # this file: project context for Claude Code
├── README.md                  # human-facing overview, pass criteria, attribution
├── LICENSE                    # MIT (covers this repo's original content)
└── data/
    ├── golden.jsonl           # 40 Q&A pairs grounded in playwright.dev
    └── adversarial.jsonl      # ~35 jailbreak / prompt-injection / off-topic cases
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

## Conventions

- Golden answers must be **verified against the live docs** at the time of writing. If the docs change, update `expected_answer` and keep the `id`.
- `expected_answer` is a paraphrase, not a copy of docs text; keep any quote short. Source attribution is required (Playwright docs are Apache 2.0; see README).
- Golden questions should be answerable from the docs alone, and diverse across `topic` and `difficulty`.
- Adversarial `must_not_contain` canaries should be strings that would not appear in a legitimate answer (e.g. `PWNED`), so substring matching has no false positives.
- No real secrets or real personal data in any file. Adversarial prompts use obviously fake placeholders.
- Keep one object per line so diffs and `jq`/`wc -l` work. Validate with `python -c "import json,sys; [json.loads(l) for l in open(sys.argv[1])]" data/<file>.jsonl`.

## Git workflow

Work on a feature branch (not `main`), one commit per logical step, and open a PR when the set is ready.
