"""One row per pull request with exposure (measured when it is opened or merged) and the outcomes.

Usage: python build_outcomes.py DATA_DIR REPOS_SAMPLE_CSV OUT_PARQUET
Needs DATA_DIR/pr_table.parquet (build_pr_table.py), DATA_DIR/lines/* (git_line_edges.py), DATA_DIR/issues/*.jsonl.

Exposure, fixed at the moment the pull request is opened (never from how long it stayed open):
  others_open        agent pull requests of other launchers that are open at that moment
  others_open_diffco of those, the ones made with a different product than this pull request
  own_open           other agent pull requests of the same launcher open at that moment
  other_users_30d    other launchers who opened an agent pull request in the previous 30 days
Outcomes:
  merged, hours_to_merge, hours_to_close
  ci_head, ci_merge  test status of the last commit of the pull request and of the commit that merged it
  broke_main         merged, green on its own, red on the default branch right after the merge
  reverted, reverted_by_other, days_to_revert
  added_lines        lines the pull request put on the default branch (generated and lock files excluded)
  lost_30d           of those, lines deleted within 30 days of the merge by a later pull request
  lost_30d_other     ... by a pull request of a different launcher
  lost_30d_other_agent  ... of a different launcher using an agent
  lost_30d_concurrent   ... of a different launcher whose pull request was already open when this one merged
  issue_shared       the pull request closes an issue that a pull request of another launcher also closes
"""
import collections
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

data, sample_csv, out = sys.argv[1], sys.argv[2], sys.argv[3]
d = pd.read_parquet(f"{data}/pr_table.parquet")
for c in ("created_at", "merged_at", "closed_at"):
    d[c] = pd.to_datetime(d[c], utc=True)
d = d.merge(pd.read_csv(sample_csv)[["full_name", "cell_users", "cell_companies", "stars", "language"]]
            .rename(columns={"full_name": "repo"}), on="repo", how="left")
d["is_agent"] = d.agent.notna()
d["merged"] = d.merged_at.notna()
d["hours_to_merge"] = (d.merged_at - d.created_at).dt.total_seconds() / 3600
d["hours_to_close"] = (d.closed_at - d.created_at).dt.total_seconds() / 3600
d["ci_head"], d["ci_merge"] = d.status_head, d.status_merge
d["broke_main"] = np.where(d.merged & (d.status_head == "SUCCESS") & d.status_merge.isin(["SUCCESS", "FAILURE", "ERROR"]),
                           d.status_merge.isin(["FAILURE", "ERROR"]).astype(float), np.nan)
NS = lambda s: s.astype("int64").to_numpy()
FAR = np.iinfo("int64").max

# ---- exposure at opening -------------------------------------------------------------------------------------------
for c in ("others_open", "others_open_diffco", "own_open", "other_users_30d"):
    d[c] = 0
for repo, g in d.groupby("repo", sort=False):
    a = g[g.is_agent & g.launcher.notna()]
    if a.empty:
        continue
    t = NS(g.created_at)
    a_open = NS(a.created_at)
    a_end = np.where(a.closed_at.isna(), FAR, NS(a.closed_at.fillna(pd.Timestamp("2100-01-01", tz="UTC"))))
    a_who, a_prod, a_num = a.launcher.to_numpy(), a.agent.to_numpy(), a.number.to_numpy()
    who, prod, num = g.launcher.to_numpy(), g.agent.to_numpy(), g.number.to_numpy()
    res = np.zeros((len(g), 4), dtype=int)
    month = 30 * 86400 * 10**9
    for i in range(len(g)):
        live = (a_open < t[i]) & (a_end > t[i]) & (a_num != num[i])
        other = a_who != who[i]
        res[i, 0] = (live & other).sum()
        res[i, 1] = (live & other & (a_prod != prod[i])).sum() if prod[i] is not None else 0
        res[i, 2] = (live & ~other).sum()
        recent = (a_open < t[i]) & (a_open >= t[i] - month) & other
        res[i, 3] = len(set(a_who[recent]))
    d.loc[g.index, ["others_open", "others_open_diffco", "own_open", "other_users_30d"]] = res

# ---- commits on the default branch -> pull request ------------------------------------------------------------------
NUM = re.compile(r"\(#(\d+)\)\s*$|^Merge pull request #(\d+) ")
for c in ("added_lines", "lost_30d", "lost_30d_other", "lost_30d_other_agent", "lost_30d_concurrent", "lost_30d_whole_file"):
    d[c] = np.nan
d["reverted"], d["reverted_by_other"], d["days_to_revert"], d["has_git"] = False, False, np.nan, False
stats = collections.Counter()
by_repo = {r: g for r, g in d.groupby("repo", sort=False)}
for f in sorted(glob.glob(f"{data}/lines/*.done")):
    key = os.path.basename(f)[:-5]
    repo = key.replace("__", "/", 1)
    if repo not in by_repo:
        continue
    g = by_repo[repo]
    commits = pd.read_csv(f"{data}/lines/{key}.commits.csv", dtype={"subject": str}).fillna({"subject": ""})
    edges = pd.read_csv(f"{data}/lines/{key}.edges.csv")
    reverts = pd.read_csv(f"{data}/lines/{key}.reverts.csv", dtype=str)
    by_oid = {o: n for o, n in zip(g.merge_oid, g.number) if isinstance(o, str)}
    known = set(g.number)

    def pr_of(oid, subject):
        if oid in by_oid:
            return by_oid[oid]
        m = NUM.search(subject)
        n = int(m.group(1) or m.group(2)) if m else None
        return n if n in known else None

    commits["pr"] = [pr_of(o, s) for o, s in zip(commits.oid, commits.subject)]
    stats["commits"] += len(commits)
    stats["commits_with_pr"] += commits.pr.notna().sum()
    c2pr = dict(zip(commits.oid, commits.pr))
    c2t = dict(zip(commits.oid, commits.time))
    info = g.set_index("number")[["launcher", "is_agent", "created_at", "merged_at"]]
    d.loc[g.index, "has_git"] = True
    added = commits.dropna(subset=["pr"]).groupby("pr").added.sum()
    idx = dict(zip(g.number, g.index))
    for n, v in added.items():
        d.at[idx[n], "added_lines"] = v
    acc = collections.defaultdict(lambda: np.zeros(5))
    for dl, og, lines, _, whole in edges.itertuples(index=False):
        A, B = c2pr.get(og), c2pr.get(dl)
        if A is None or pd.isna(A) or (B is not None and not pd.isna(B) and A == B):
            continue
        if not 0 <= c2t[dl] - c2t[og] <= 30 * 86400:
            continue
        v = acc[A]
        v[0] += lines
        v[4] += whole
        if B is None or pd.isna(B):
            continue
        la, lb = info.at[A, "launcher"], info.at[B, "launcher"]
        if la is not None and lb is not None and la != lb:
            v[1] += lines
            if info.at[B, "is_agent"]:
                v[2] += lines
            if pd.notna(info.at[A, "merged_at"]) and info.at[B, "created_at"] < info.at[A, "merged_at"]:
                v[3] += lines
    for n in added.index:
        v = acc.get(n, np.zeros(5))
        d.loc[idx[n], ["lost_30d", "lost_30d_other", "lost_30d_other_agent", "lost_30d_concurrent", "lost_30d_whole_file"]] = v
    # reverts: by commit id, and by the title GitHub gives to a revert pull request
    oids = list(by_oid)
    for rv, t, target in reverts.itertuples(index=False):
        hit = [o for o in oids if o.startswith(target)]
        A, B = (by_oid[hit[0]] if hit else None), c2pr.get(rv)
        if A is None:
            continue
        i = idx[A]
        d.at[i, "reverted"] = True
        if pd.notna(d.at[i, "merged_at"]):
            d.at[i, "days_to_revert"] = (int(t) - d.at[i, "merged_at"].timestamp()) / 86400
        if B is not None and not pd.isna(B) and info.at[B, "launcher"] not in (None, info.at[A, "launcher"]):
            d.at[i, "reverted_by_other"] = True
# reverts by title, for every repository (also the ones without a clone)
for repo, g in d.groupby("repo", sort=False):
    rev = g[g.title.str.startswith('Revert "', na=False) & g.merged]
    if rev.empty:
        continue
    first = g[g.merged].sort_values("merged_at").drop_duplicates("title").set_index("title")
    for _, r in rev.iterrows():
        inner = r.title[8:].rstrip('"')
        if inner in first.index and first.at[inner, "merged_at"] <= r.merged_at and first.at[inner, "number"] != r.number:
            i = g.index[g.number == first.at[inner, "number"]][0]
            if not d.at[i, "reverted"]:
                d.at[i, "days_to_revert"] = (r.merged_at - d.at[i, "merged_at"]).total_seconds() / 86400
            d.at[i, "reverted"] = True
            if r.launcher is not None and d.at[i, "launcher"] is not None and r.launcher != d.at[i, "launcher"]:
                d.at[i, "reverted_by_other"] = True

# ---- issues closed by pull requests of more than one launcher -------------------------------------------------------
d["closes_issue"], d["issue_shared"] = False, False
for f in sorted(glob.glob(f"{data}/issues/*.jsonl")):
    repo = os.path.basename(f)[:-6].replace("__", "/", 1)
    if repo not in by_repo:
        continue
    g = by_repo[repo]
    who = dict(zip(g.number, g.launcher))
    idx = dict(zip(g.number, g.index))
    for line in open(f):
        it = json.loads(line)
        prs = {x["number"] for x in (it["closedByPullRequestsReferences"]["nodes"] or []) if x}
        prs |= {t["source"]["number"] for t in (it["timelineItems"]["nodes"] or []) if t
                and t.get("__typename") == "CrossReferencedEvent" and t.get("willCloseTarget") and (t.get("source") or {}).get("number")}
        prs = [n for n in prs if n in who]
        people = {who[n] for n in prs if who[n] is not None}
        for n in prs:
            d.at[idx[n], "closes_issue"] = True
            if len(people - {who[n]}) >= 1:
                d.at[idx[n], "issue_shared"] = True

d.to_parquet(out, index=False)
print(len(d), "pull requests;", int(d.has_git.sum()), "in repositories with line data;",
      f"{stats['commits_with_pr']}/{stats['commits']} default-branch commits matched to a pull request")
print("merged with added_lines:", int(d.added_lines.notna().sum()), "| reverted:", int(d.reverted.sum()),
      "| closes issue:", int(d.closes_issue.sum()), "| issue shared:", int(d.issue_shared.sum()))
