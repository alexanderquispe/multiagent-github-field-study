"""Merge rate of an agent pull request by whether another user's agent pull request was open when it was opened.

Usage: python exposure_at_opening.py AIDEV_DIR [MAX_PRS_PER_USER]
Human-opened agent pull requests only (Codex, Claude Code, Cursor: the opener is the person who launched the agent),
in repositories with at least two such users. Exposure is fixed at the moment of opening (how many agent pull
requests of OTHER users, and of the SAME user, are open at that instant), so it cannot depend on what later happens
to the pull request. Pull requests opened in the last 30 days of the data are dropped (their outcome is not known).
The comparison is within repository and user; standard errors are across repositories.
"""
import math
import sys

import numpy as np
import pandas as pd

src = sys.argv[1]
cap = int(sys.argv[2]) if len(sys.argv) > 2 else 0
BOTS = {"Copilot", "devin-ai-integration[bot]", "cursor[bot]"}
df = pd.read_parquet(f"{src}/pull_request.parquet",
                     columns=["number", "agent", "user", "created_at", "closed_at", "merged_at", "repo_id"])
df = df[~df.user.isin(BOTS) & ~df.user.str.endswith("[bot]")].copy()
for c in ("created_at", "closed_at", "merged_at"):
    df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
if cap:
    n = df.groupby("user").size()
    df = df[df.user.isin(n[n <= cap].index)]
gmax = df.created_at.max()
df["end"] = df.closed_at.fillna(gmax + pd.Timedelta(days=1))
df["merged"] = df.merged_at.notna().astype(float)
users = df.groupby("repo_id").user.nunique()
df = df[df.repo_id.isin(users[users >= 2].index)].sort_values(["repo_id", "created_at"])
other, own = [], []
for _, g in df.groupby("repo_id", sort=False):
    s, e, u = g.created_at.values, g.end.values, g.user.values
    for i in range(len(g)):
        op = (s[:i] < s[i]) & (e[:i] > s[i])  # opened earlier and still open (rows are sorted by opening time)
        other.append(int((op & (u[:i] != u[i])).sum()))
        own.append(int((op & (u[:i] == u[i])).sum()))
df["open_other"], df["open_own"] = other, own
df = df[df.created_at <= gmax - pd.Timedelta(days=30)]
print(f"data: {src} | pull requests {len(df)}, repositories {df.repo_id.nunique()}, users {df.user.nunique()}, "
      f"{df.created_at.min():%Y-%m} to {df.created_at.max():%Y-%m}" + (f" | users with at most {cap} pull requests" if cap else ""))
print("\nmerge rate by number of other users' agent pull requests open at opening:")
print(df.groupby(pd.cut(df.open_other, [-1, 0, 1, 3, 10 ** 6], labels=["0", "1", "2-3", "4+"]), observed=True)
      .merged.agg(["mean", "size"]).round(3).to_string())


def within(flag, name):
    t = df.assign(x=flag).groupby(["repo_id", "user", "x"]).merged.agg(["mean", "size"]).unstack().dropna()
    d = t[("mean", True)] - t[("mean", False)]
    w = np.minimum(t[("size", True)], t[("size", False)])
    dr = (d * w).groupby(level="repo_id").sum() / w.groupby(level="repo_id").sum()
    print(f"{name}: {len(t)} user-repositories in {len(dr)} repositories; merge rate {100 * t[('mean', True)].mean():.1f}% "
          f"against {100 * t[('mean', False)].mean():.1f}%; difference {100 * dr.mean():+.1f} points "
          f"(standard error {100 * dr.std(ddof=1) / math.sqrt(len(dr)):.1f})")


print("\nwithin repository and user:")
within(df.open_other > 0, "another user's agent pull request open, against none")
within(df.open_other >= 2, "two or more of other users open, against fewer")
within(df.open_own > 0, "the user's own other agent pull request open, against none (comparison)")
