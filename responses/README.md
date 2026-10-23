# SUT responses for the CI quality gate

Commit your SUT's responses here to have CI score them. Each file is JSONL of `{"id", "response"}`
(golden rows may also carry `contexts` and `citations`, see the main README):

- `golden.jsonl`
- `adversarial.jsonl`
- `unanswerable.jsonl`

Missing files are skipped. Thresholds live in `gate.json`.
