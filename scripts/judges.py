"""Judge providers for score.py: Anthropic Messages API or GitHub Models (free tier, GITHUB_TOKEN)."""
import json, os, time, urllib.error, urllib.request

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "github": "openai/gpt-4.1"}
GITHUB_URL = "https://models.github.ai/inference/chat/completions"
RETRY_STATUS = {429, 500, 502, 503, 504}


def _post(url, headers, payload, retries=4, sleep=time.sleep):
    """POST JSON, retrying rate limits and transient errors with exponential backoff (honours Retry-After)."""
    body = json.dumps(payload).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers={"content-type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == retries:
                raise
            try:
                wait = float(e.headers.get("Retry-After", ""))
            except (TypeError, ValueError):
                wait = 2 ** (attempt + 1)
            sleep(min(wait, 60))


def anthropic_judge(model):
    def judge(prompt):
        d = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
                  {"model": model, "max_tokens": 400, "temperature": 0,
                   "messages": [{"role": "user", "content": prompt}]})
        return d["content"][0]["text"]
    return judge


def github_judge(model):
    def judge(prompt):
        d = _post(GITHUB_URL, {"authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                               "accept": "application/vnd.github+json"},
                  {"model": model, "max_tokens": 400, "temperature": 0,
                   "messages": [{"role": "user", "content": prompt}]})
        return d["choices"][0]["message"]["content"]
    return judge


def resolve_provider(provider, env=os.environ):
    """auto: Anthropic if ANTHROPIC_API_KEY is set, else GitHub Models if GITHUB_TOKEN is set, else None."""
    if provider == "auto":
        return "anthropic" if env.get("ANTHROPIC_API_KEY") else "github" if env.get("GITHUB_TOKEN") else None
    return provider


def make_judge(provider, model=None):
    provider = resolve_provider(provider)
    if provider is None:
        return None
    return {"anthropic": anthropic_judge, "github": github_judge}[provider](model or DEFAULT_MODELS[provider])
