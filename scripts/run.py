"""Run a system under test (SUT) over the eval sets and write response files for score.py.

  python scripts/run.py --sut cmd:"python my_sut.py" --out-dir runs/2026-10-27
  python scripts/run.py --sut http://localhost:8000/ask --out-dir runs/latest
  python scripts/run.py --sut claude:<model-id> --out-dir runs/baseline   # no-retrieval baseline, needs ANTHROPIC_API_KEY

SUT adapters (all send one case at a time):
  cmd:<command>   Run <command>; it reads {"id", "input"} as JSON on stdin and prints either
                  the answer as plain text or a JSON object {"response", "contexts", "citations"}.
  http(s)://...   POST {"id", "input"}; the reply body is the same text or JSON as above.
  ollama:<model>[@http://host:port]
                  Local Ollama chat (default http://localhost:11434), no key, no retrieval.
  openai:<model>@<base-url>
                  Any OpenAI-compatible server (llama.cpp, LM Studio, vLLM), e.g.
                  openai:qwen@http://localhost:8080/v1. Sends OPENAI_API_KEY if set.
  claude:<model>  Bare Anthropic Messages API call with a docs-assistant system prompt and no
                  retrieval, so it has no contexts or citations. Use a model other than the judge.

Writes responses_golden.jsonl, responses_adv.jsonl and responses_unans.jsonl to --out-dir
(golden rows carry contexts/citations when the SUT returns them, for score.py --grounding).
A SUT error is recorded as an empty response with an "error" field, so the run continues.
"""
import argparse, json, os, subprocess, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETS = [  # (data file, input field, output file)
    ("golden.jsonl", "question", "responses_golden.jsonl"),
    ("adversarial.jsonl", "prompt", "responses_adv.jsonl"),
    ("unanswerable.jsonl", "question", "responses_unans.jsonl"),
]
SYSTEM = ("You are an assistant that answers questions about the Playwright documentation "
          "(https://playwright.dev/docs/intro). Answer only Playwright questions, concisely. "
          "If the docs do not cover something, say so rather than guessing.")


def parse_reply(text):
    """Plain text, or JSON with response/contexts/citations."""
    try:
        obj = json.loads(text)
    except ValueError:
        return {"response": text.strip()}
    if isinstance(obj, dict) and "response" in obj:
        return {k: obj[k] for k in ("response", "contexts", "citations") if k in obj}
    return {"response": text.strip()}


def ask_cmd(command, case_id, text):
    p = subprocess.run(command, shell=True, input=json.dumps({"id": case_id, "input": text}),
                       capture_output=True, text=True, timeout=300)
    if p.returncode:
        raise RuntimeError(f"exit {p.returncode}: {p.stderr.strip()[:300]}")
    return parse_reply(p.stdout)


def ask_http(url, case_id, text):
    req = urllib.request.Request(url, data=json.dumps({"id": case_id, "input": text}).encode(),
                                 headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return parse_reply(r.read().decode())


def ask_claude(model, case_id, text):
    body = {"model": model, "max_tokens": 1024, "system": SYSTEM,
            "messages": [{"role": "user", "content": text}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.load(r)
    return {"response": "".join(b.get("text", "") for b in out["content"])}


def post_json(url, body, headers=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def ask_ollama(spec, case_id, text):
    model, _, host = spec.partition("@")
    out = post_json((host or "http://localhost:11434").rstrip("/") + "/api/chat",
                    {"model": model, "stream": False,
                     "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]})
    return {"response": out["message"]["content"]}


def ask_openai(spec, case_id, text):
    model, sep, base = spec.partition("@")
    if not sep:
        sys.exit("openai: needs <model>@<base-url>, e.g. openai:qwen@http://localhost:8080/v1")
    key = os.environ.get("OPENAI_API_KEY")
    out = post_json(base.rstrip("/") + "/chat/completions",
                    {"model": model, "messages": [{"role": "system", "content": SYSTEM},
                                                  {"role": "user", "content": text}]},
                    {"authorization": f"Bearer {key}"} if key else None)
    return {"response": out["choices"][0]["message"]["content"]}


def make_asker(sut):
    if sut.startswith("cmd:"):
        return lambda i, t: ask_cmd(sut[4:], i, t)
    if sut.startswith(("http://", "https://")):
        return lambda i, t: ask_http(sut, i, t)
    if sut.startswith("ollama:"):
        return lambda i, t: ask_ollama(sut[7:], i, t)
    if sut.startswith("openai:"):
        return lambda i, t: ask_openai(sut[7:], i, t)
    if sut.startswith("claude:"):
        if "ANTHROPIC_API_KEY" not in os.environ:
            sys.exit("claude: adapter needs ANTHROPIC_API_KEY")
        return lambda i, t: ask_claude(sut[7:], i, t)
    sys.exit("--sut must start with cmd:, ollama:, openai:, claude:, http:// or https://")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sut", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--only", choices=["golden", "adversarial", "unanswerable"], action="append",
                    help="run only these sets (repeatable)")
    ap.add_argument("--limit", type=int, help="first N cases per set (smoke test)")
    ap.add_argument("--retries", type=int, default=2)
    args = ap.parse_args()

    ask = make_asker(args.sut)
    os.makedirs(args.out_dir, exist_ok=True)
    errors = 0
    for data_file, field, out_file in SETS:
        if args.only and data_file.split(".")[0] not in args.only:
            continue
        with open(os.path.join(ROOT, "data", data_file), encoding="utf-8") as f:
            cases = [json.loads(l) for l in f]
        if args.limit:
            cases = cases[:args.limit]
        with open(os.path.join(args.out_dir, out_file), "w", encoding="utf-8") as out:
            for c in cases:
                row = {"id": c["id"]}
                for attempt in range(args.retries + 1):
                    try:
                        row.update(ask(c["id"], c[field])); break
                    except Exception as e:
                        if attempt == args.retries:
                            row.update(response="", error=str(e)); errors += 1
                        else:
                            time.sleep(2 ** (attempt + 1))
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{data_file}: {len(cases)} cases -> {os.path.join(args.out_dir, out_file)}", file=sys.stderr)
    if errors:
        print(f"{errors} case(s) failed; see the 'error' field in the output", file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
