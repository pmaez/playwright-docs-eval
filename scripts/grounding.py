"""RAG grounding checks for golden-set responses. See rubrics/grounding.json."""
import re
from urllib.parse import urlparse

CODE_SPAN = re.compile(r"`([^`\n]{2,80})`")


def page(url):
    """Normalise a docs URL to host+path (no scheme, fragment, query or trailing slash)."""
    u = urlparse(url.strip())
    return (u.netloc.lower() + u.path.rstrip("/")).lower()


def unsupported_identifiers(response, contexts):
    corpus = " ".join(c.get("text", "") for c in contexts).lower()
    out = []
    for span in CODE_SPAN.findall(response):
        s = span.strip().rstrip("();,").lower()
        if len(s) >= 3 and s not in corpus and span not in out:
            out.append(span)
    return out


def deterministic(case, resp):
    ctx = resp.get("contexts") or []
    cites = resp.get("citations") or []
    ctx_pages = {page(c["url"]) for c in ctx if c.get("url")}
    want = page(case["source_url"])
    return {
        "retrieval_hit": want in ctx_pages,
        "cited": bool(cites),
        "citation_correct": any(page(c) == want for c in cites),
        "citations_valid": all(urlparse(c).scheme == "https" and urlparse(c).netloc.lower() == "playwright.dev" for c in cites),
        "citations_in_context": all(page(c) in ctx_pages for c in cites),
        "unsupported_identifiers": unsupported_identifiers(resp["response"], ctx),
    }


def faithfulness_prompt(rubric, contexts, response):
    c = rubric["judge_criteria"][0]
    ctx = "\n\n".join(f"[{i + 1}] {x.get('url', '')}\n{x.get('text', '')}" for i, x in enumerate(contexts))
    return (f"You are checking whether an answer is grounded in retrieved documentation.\n\n"
            f"Retrieved contexts:\n<contexts>\n{ctx}\n</contexts>\n\n"
            f"Response to check:\n<response>\n{response}\n</response>\n\n"
            f"{c['question']} Levels: {c['levels']}\n{rubric['notes']}\n"
            'Reply with only JSON like {"faithfulness": 2, "reason": "<one sentence>"}.')


def score_grounding(cases, responses, rubric, judge, parse_scores):
    rows = []
    for c in cases:
        r = responses.get(c["id"])
        if r is None or "contexts" not in r:
            rows.append({"id": c["id"], "topic": c["topic"], "pass": None, "error": "no contexts supplied"})
            continue
        d = deterministic(c, r)
        row = {"id": c["id"], "topic": c["topic"], "difficulty": c["difficulty"], **d}
        gate = d["citations_valid"] and d["citations_in_context"]
        if not gate:
            row["pass"] = False
        elif judge is None:
            row["pass"] = None
        else:
            row["faithfulness"] = parse_scores(judge(faithfulness_prompt(rubric, r["contexts"], r["response"])))["faithfulness"]
            row["pass"] = row["faithfulness"] == 2
        rows.append(row)
    return rows


def summarize(rows):
    have = [r for r in rows if "retrieval_hit" in r]
    if not have:
        print("  no responses with contexts"); return
    n = len(have)
    pct = lambda k: f"{sum(bool(r[k]) for r in have)}/{n}"
    print(f"  retrieval_hit {pct('retrieval_hit')}, cited {pct('cited')}, citation_correct {pct('citation_correct')}, "
          f"citations_valid {pct('citations_valid')}, citations_in_context {pct('citations_in_context')}")
    print(f"  cases with unsupported identifiers: {sum(bool(r['unsupported_identifiers']) for r in have)}/{n}")
    print(f"  citation gate failures (invalid or fabricated citations): {sum(r['pass'] is False and 'faithfulness' not in r for r in have)}/{n}")
    judged = [r for r in have if "faithfulness" in r]
    if judged:
        print(f"  faithfulness == 2 (among cases past the citation gate): {sum(r['pass'] for r in judged)}/{len(judged)}")
