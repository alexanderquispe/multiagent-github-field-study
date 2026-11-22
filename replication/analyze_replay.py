"""Conflict rates from the merge replay: the paper's table, a check against the authors' labels, and the split by user.

Usage: python analyze_replay.py   (from this folder, after replay_pairs.py has written results/)
Reads pairs_paper_sample.csv, pairs_user_sample.csv, results/replay_*.csv and the authors' rq3_merge_replay_full.csv.
Writes results/summary.md.
"""
import math

import pandas as pd

THEIRS = "../external/concurrent-agentic-prs-replication/rq3_merge_replay_full.csv"
KEY = ["repo", "prA", "prB"]
out = []


def say(text=""):
    print(text)
    out.append(text)


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def rate(g):
    k, n = int((g.label == "CONFLICT").sum()), len(g)
    p, lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * p:.1f}% ({100 * lo:.1f} to {100 * hi:.1f})"


def evaluable(d):
    return d[d.label.isin(["CLEAN", "CONFLICT"])]


# 1. the paper's sample, replayed here
ours = pd.read_csv("pairs_paper_sample.csv").merge(pd.read_csv("results/replay_paper_sample.csv"), on=KEY)
theirs = pd.read_csv(THEIRS)
say("## 1. The paper's 747 pairs, replayed on our cluster\n")
say(f"Labels here: {ours.label.value_counts().to_dict()}")
say(f"Labels in the authors' file: {theirs.label.value_counts().to_dict()}\n")
say("| Stratum | Authors | Our replay |")
say("|---|---|---|")
for s in ["same", "cross"]:
    say(f"| {s}-agent | {rate(evaluable(theirs[theirs.stratum == s]))} | {rate(evaluable(ours[ours.stratum == s]))} |")
m = ours.merge(theirs, on=["stratum"] + KEY, suffixes=("", "_theirs"))
both = m[m.label.isin(["CLEAN", "CONFLICT"]) & m.label_theirs.isin(["CLEAN", "CONFLICT"])]
say(f"\nPairs evaluable in both runs: {len(both)}; same label in {int((both.label == both.label_theirs).sum())}; "
    f"same conflicted files in {int((both.files.fillna('') == both.files_theirs.fillna('')).sum())}.")
say(f"Pairs that changed availability: {int((m.label.str.startswith('UNAVAIL') != m.label_theirs.str.startswith('UNAVAIL')).sum())}.")

# 2. the same sample, split by who opened the pull requests
BOTS = {"Copilot", "devin-ai-integration[bot]", "cursor[bot]"}
is_bot = lambda u: u in BOTS or str(u).endswith("[bot]")
h = evaluable(ours)
h = h[~h.userA.map(is_bot) & ~h.userB.map(is_bot)].copy()
h["same_user"] = h.userA == h.userB
say("\n## 2. The paper's sample, split by who opened the two pull requests\n")
say(f"Pairs with both pull requests opened by a human account: {len(h)} of {len(evaluable(ours))}.\n")
say("| Agents | Users | Conflict rate |")
say("|---|---|---|")
for s in ["same", "cross"]:
    for su in [True, False]:
        say(f"| {s}-agent | {'same user' if su else 'different users'} | {rate(h[(h.stratum == s) & (h.same_user == su)])} |")

# 3. our sample: up to 10 same-user and 10 different-user pairs per repository
u = pd.read_csv("pairs_user_sample.csv").merge(pd.read_csv("results/replay_user_sample.csv"), on=KEY)
say("\n## 3. Within-repository sample (repositories with at least one different-user pair)\n")
say(f"Labels: {u.label.value_counts().to_dict()}; repositories: {u.repo.nunique()}.\n")
e = evaluable(u).copy()
e["conf"] = (e.label == "CONFLICT").astype(float)
say("| Agents | Users | Pairs pooled | Mean of repository rates | Repositories |")
say("|---|---|---|---|---|")
for s in ["same", "cross"]:
    for su in [True, False]:
        g = e[(e.stratum == s) & (e.same_user == su)]
        r = g.groupby("repo").conf.mean()
        say(f"| {s}-agent | {'same user' if su else 'different users'} | {rate(g)} | {100 * r.mean():.1f}% | {len(r)} |")
# paired comparison: repositories with both kinds of pair, same-agent stratum
g = e[e.stratum == "same"].groupby(["repo", "same_user"]).conf.mean().unstack()
g = g.dropna()
diff = g[False] - g[True]
se = diff.std(ddof=1) / math.sqrt(len(diff)) if len(diff) > 1 else float("nan")
say(f"\nSame-agent pairs, repositories that have both kinds ({len(g)}): different users {100 * g[False].mean():.1f}%, "
    f"same user {100 * g[True].mean():.1f}%, difference {100 * diff.mean():+.1f} points "
    f"(standard error {100 * se:.1f}; {int((diff > 0).sum())} repositories higher, {int((diff < 0).sum())} lower, "
    f"{int((diff == 0).sum())} equal).")
e["nm"] = e.mergedA.astype(int) + e.mergedB.astype(int)
say("\nPairs by how many of the two pull requests were merged in reality (0, 1, 2), and conflict rate:\n")
say("| Users | Merged 0 | Merged 1 | Merged 2 |")
say("|---|---|---|---|")
for su in [True, False]:
    say(f"| {'same user' if su else 'different users'} | " + " | ".join(rate(e[(e.same_user == su) & (e.nm == k)]) for k in (0, 1, 2)) + " |")
open("results/summary.md", "w").write("\n".join(out) + "\n")
