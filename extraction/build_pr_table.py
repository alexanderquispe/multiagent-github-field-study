"""One row per pull request, with our agent label and the person who launched it.

Usage: python build_pr_table.py DATA_DIR OUT_PARQUET
Reads DATA_DIR/prs/*.jsonl (from fetch_prs.py). Agent label, first rule that matches:
  Copilot / Devin / Jules / Cursor: the account that opened the pull request is that product's bot;
  Codex: branch codex/... or a chatgpt.com/codex link in the description;
  Cursor: branch cursor/... or a commit by cursoragent@cursor.com;
  Claude Code: "Generated with Claude Code" in the description or a commit, an anthropic.com co-author, or branch claude/...
Launcher: the account that opened the pull request if it is a person; for a bot, the first assigned person.
"""
import glob
import json
import re
import sys

import pandas as pd

BOT_PRODUCT = {"copilot-swe-agent": "Copilot", "Copilot": "Copilot", "devin-ai-integration": "Devin",
               "google-labs-jules": "Google_Jules", "cursor": "Cursor", "claude": "Claude_Code",
               "chatgpt-codex-connector": "OpenAI_Codex"}
CLAUDE = re.compile(r"Generated with \[?Claude Code|noreply@anthropic\.com|claude\.ai/code", re.I)


def label(p, login, is_bot, msgs, emails):
    body, head = p["body"] or "", p["headRefName"] or ""
    found = []
    if is_bot and login in BOT_PRODUCT:
        found.append(BOT_PRODUCT[login])
    if head.startswith("codex/") or "chatgpt.com/codex" in body:
        found.append("OpenAI_Codex")
    if head.startswith("cursor/") or "cursoragent@cursor.com" in emails or "cursor.com/background-agent" in body:
        found.append("Cursor")
    if head.startswith("copilot/"):
        found.append("Copilot")
    if CLAUDE.search(body) or CLAUDE.search(msgs) or "noreply@anthropic.com" in emails or head.startswith("claude/"):
        found.append("Claude_Code")
    found = list(dict.fromkeys(found))
    return (found[0] if found else None), "+".join(found)


rows = []
for f in sorted(glob.glob(sys.argv[1] + "/prs/*.jsonl")):
    repo = f.split("/")[-1][:-6].replace("__", "/", 1)
    for line in open(f):
        p = json.loads(line)
        a = p["author"] or {}
        login, is_bot = a.get("login"), a.get("__typename") == "Bot"
        commits = p["commits"]["nodes"]
        msgs = "\n".join(c["commit"]["message"] for c in commits)
        emails = " ".join((x.get("email") or "") for c in commits for x in c["commit"]["authors"]["nodes"])
        agent, signals = label(p, login, is_bot, msgs, emails)
        people = [x["login"] for x in p["assignees"]["nodes"] if x["login"] not in BOT_PRODUCT]
        launcher = login if not is_bot else (people[0] if people else None)
        mc = p["mergeCommit"] or {}
        last = commits[-1]["commit"] if commits else {}
        rows.append(dict(
            repo=repo, number=p["number"], author=login, author_is_bot=is_bot, launcher=launcher, agent=agent,
            signals=signals, created_at=p["createdAt"], merged_at=p["mergedAt"], closed_at=p["closedAt"],
            state=p["state"], head_ref=p["headRefName"], base_ref=p["baseRefName"], head_oid=p["headRefOid"],
            base_oid=p["baseRefOid"], merge_oid=mc.get("oid"), merged_by=(p["mergedBy"] or {}).get("login"),
            cross_repo=p["isCrossRepository"], additions=p["additions"], deletions=p["deletions"],
            changed_files=p["changedFiles"], n_commits=p["commits"]["totalCount"],
            n_reviews=p["reviews"]["totalCount"], n_comments=p["comments"]["totalCount"],
            status_merge=(mc.get("statusCheckRollup") or {}).get("state"),
            status_head=(last.get("statusCheckRollup") or {}).get("state"), title=p["title"]))
d = pd.DataFrame(rows)
d.to_parquet(sys.argv[2], index=False)
print(len(d), "pull requests,", d.repo.nunique(), "repositories")
print(d.agent.fillna("none").value_counts().to_string())
