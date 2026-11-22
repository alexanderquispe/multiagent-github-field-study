"""Download pull request metadata for the sampled repositories with the GitHub GraphQL API.

Usage: python fetch_prs.py REPOS_CSV OUT_DIR [--limit N] [--since 2025-01-01] [--workers 4]
REPOS_CSV needs a column full_name (owner/name). Tokens are read from ../.env (GITHUB_TOKEN*), never printed.
Writes OUT_DIR/prs/OWNER__NAME.jsonl (one pull request per line, newest first) and OUT_DIR/repos/OWNER__NAME.json.
A repository is skipped if its .json already exists; an interrupted one resumes from its .cursor file.
One request at a time per token, so more workers than tokens does not help.
"""
import argparse
import concurrent.futures as cf
import json
import os
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CTX = ssl.create_default_context(cafile="/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")
PAGE = 50

QUERY = """
query($owner:String!, $name:String!, $cursor:String, $n:Int = 50) {
  rateLimit { remaining resetAt cost }
  repository(owner:$owner, name:$name) {
    nameWithOwner diskUsage isFork isArchived stargazerCount createdAt pushedAt
    defaultBranchRef { name target { oid } }
    mergeCommitAllowed squashMergeAllowed rebaseMergeAllowed
    pullRequests(first:$n, after:$cursor, orderBy:{field:CREATED_AT, direction:DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body state isDraft createdAt mergedAt closedAt
        author { __typename login }
        mergedBy { __typename login }
        headRefName headRefOid baseRefName baseRefOid isCrossRepository
        additions deletions changedFiles
        mergeCommit { oid statusCheckRollup { state } }
        labels(first:10) { nodes { name } }
        assignees(first:5) { nodes { login } }
        reviews(first:20) { totalCount nodes { author { __typename login } state submittedAt } }
        comments { totalCount }
        timelineItems(itemTypes:[ASSIGNED_EVENT], first:5) {
          nodes { ... on AssignedEvent { createdAt actor { __typename login }
                  assignee { __typename ... on User { login } ... on Bot { login } } } }
        }
        commits(first:30) {
          totalCount
          nodes { commit { oid committedDate message statusCheckRollup { state }
                  authors(first:5) { nodes { name email user { login } } } } }
        }
      }
    }
  }
}
"""


def load_tokens():
    tokens = []
    for line in open(os.path.join(HERE, "..", ".env")):
        if line.startswith("GITHUB_TOKEN") and "=" in line:
            tokens.append(line.split("=", 1)[1].strip())
    return tokens


TOKENS = load_tokens()
_lock = threading.Lock()
_blocked = {}  # token index -> time it can be used again
_busy = set()  # tokens with a request in flight: GitHub limits computing time per token and minute, so one at a time
_strikes = {}  # consecutive rate-limit answers per token
_next = [0]
STATS = {"ok": 0, "rate_limited": 0, "http_403_429": 0, "other_error": 0, "seconds_ok": 0.0}


def report_stats(every=60):
    """Every minute, one line to stderr: answers by kind, mean seconds per good answer, tokens resting."""
    def loop():
        prev = dict(STATS)
        while True:
            time.sleep(every)
            cur, now = dict(STATS), time.time()
            d = {k: cur[k] - prev[k] for k in cur}
            resting = sum(1 for v in _blocked.values() if v > now)
            print(time.strftime("%H:%M:%S"), f"ok={d['ok']} rate_limited={d['rate_limited']} http_403_429={d['http_403_429']} "
                  f"other_error={d['other_error']} sec_per_ok={d['seconds_ok'] / max(d['ok'], 1):.1f} tokens_resting={resting}/{len(TOKENS)} kinds={dict(sorted(KINDS.items(), key=lambda x: -x[1])[:4])}",
                  file=sys.stderr, flush=True)
            prev = cur
    threading.Thread(target=loop, daemon=True).start()


def take_token():
    """A token that is neither blocked nor in use; waits until there is one."""
    while True:
        with _lock:
            now = time.time()
            for k in range(len(TOKENS)):
                i = (_next[0] + k) % len(TOKENS)
                if i not in _busy and _blocked.get(i, 0) < now:
                    _next[0] = i + 1
                    _busy.add(i)
                    return i
        time.sleep(0.5)


KINDS = {}


def failed(kind, variables):
    """Count the error; heavy pages hit GitHub's time limit, so ask for half as many items next time."""
    STATS["other_error"] += 1
    KINDS[kind] = KINDS.get(kind, 0) + 1
    if variables.get("n", 0) > 10:
        variables["n"] = max(10, variables["n"] // 2)


def release(i, block=0):
    with _lock:
        _busy.discard(i)
        if block:
            _blocked[i] = time.time() + block


def graphql(variables, query=QUERY):
    """Rate limits never count as failures (the token rests and another one is used); other errors get 8 attempts."""
    attempt, last = 0, "?"
    while attempt < 8:
        i = take_token()
        req = urllib.request.Request(
            "https://api.github.com/graphql", data=json.dumps({"query": query, "variables": variables}).encode(),
            headers={"Authorization": "bearer " + TOKENS[i], "User-Agent": "research-client", "Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=90, context=CTX) as resp:
                d = json.load(resp)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 401:
                release(i, 86400)
            elif e.code in (403, 429):
                STATS["http_403_429"] += 1
                _strikes[i] = _strikes.get(i, 0) + 1
                release(i, min(900, 60 * 2 ** (_strikes[i] - 1)))
            else:
                failed(last, variables)
                release(i)
                attempt += 1
                time.sleep(2 + 2 * attempt)
            continue
        except Exception as e:
            last = type(e).__name__
            failed(last, variables)
            release(i)
            attempt += 1
            time.sleep(2 + 2 * attempt)
            continue
        errs = d.get("errors") or []
        if any(e.get("type") in ("RATE_LIMITED", "RATE_LIMIT") for e in errs):  # per-hour and per-minute limits
            STATS["rate_limited"] += 1
            _strikes[i] = _strikes.get(i, 0) + 1
            release(i, min(600, 20 * _strikes[i]))
            continue
        _strikes[i] = 0
        if any(e.get("type") == "NOT_FOUND" for e in errs):
            release(i)
            return None
        if d.get("data") and d["data"].get("repository"):
            STATS["ok"] += 1
            STATS["seconds_ok"] += time.time() - t0
            release(i, 900 if d["data"]["rateLimit"]["remaining"] < 50 else 0)
            return d["data"]
        release(i)
        last = "; ".join(str(e.get("type") or e.get("message"))[:60] for e in errs[:2]) or "empty answer"
        failed(last, variables)
        attempt += 1
        time.sleep(2 + 2 * attempt)  # timeouts and partial errors
    raise RuntimeError(f"no answer after 8 attempts ({last})")


def fetch(full_name, out, since):
    key = full_name.replace("/", "__")
    meta_path, pr_path = f"{out}/repos/{key}.json", f"{out}/prs/{key}.jsonl"
    tmp, ckpt = pr_path + ".tmp", pr_path + ".cursor"
    if os.path.exists(meta_path):
        return full_name, "skipped", 0
    owner, name = full_name.split("/")
    cursor, n, meta, page = None, 0, None, PAGE
    if os.path.exists(tmp) and os.path.exists(ckpt):  # resume an interrupted download
        c = json.load(open(ckpt))
        lines = open(tmp).readlines()[: c["n"]]
        if len(lines) == c["n"]:
            cursor, n, meta = c["cursor"], c["n"], c["meta"]
            open(tmp, "w").writelines(lines)
    with open(tmp, "a" if cursor else "w") as f:
        while True:
            v = {"owner": owner, "name": name, "cursor": cursor, "n": page}
            try:
                d = graphql(v)
            except RuntimeError:
                if page <= 5:
                    raise
                page = 5
                continue
            page = v["n"]  # graphql() halves it when a page is too heavy; it stays small for this repository
            if d is None:
                meta = {"full_name": full_name, "status": "not_found"}
                break
            repo = d["repository"]
            prs = repo.pop("pullRequests")
            meta = meta or dict(repo, full_name=full_name, status="ok")
            stop = False
            for pr in prs["nodes"]:
                if pr["createdAt"] < since:
                    stop = True
                    break
                f.write(json.dumps(pr, separators=(",", ":")) + "\n")
                n += 1
            if stop or not prs["pageInfo"]["hasNextPage"]:
                break
            cursor = prs["pageInfo"]["endCursor"]
            f.flush()
            json.dump({"cursor": cursor, "n": n, "meta": meta}, open(ckpt + ".new", "w"))
            os.replace(ckpt + ".new", ckpt)
    os.replace(tmp, pr_path)
    if os.path.exists(ckpt):
        os.remove(ckpt)
    meta["n_prs"] = n
    json.dump(meta, open(meta_path, "w"))
    return full_name, meta["status"], n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("repos_csv")
    ap.add_argument("out_dir")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--since", default="2025-01-01")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out_dir + "/prs", exist_ok=True)
    os.makedirs(a.out_dir + "/repos", exist_ok=True)
    names = pd.read_csv(a.repos_csv).full_name.tolist()[: a.limit]
    print(f"{len(names)} repositories, {len(TOKENS)} tokens", flush=True)
    report_stats()
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(fetch, nm, a.out_dir, a.since): nm for nm in names}
        for fut in cf.as_completed(futs):
            try:
                print(*fut.result(), flush=True)
            except Exception as e:
                print(futs[fut], "FAILED", str(e)[:120].replace(" ", "_"), flush=True)
