"""Descriptive statistics of the outcomes: distributions, by month, and by how many people use agents in the repository.

Usage: python descriptives.py PR_OUTCOMES_PARQUET OUT_DIR
Writes OUT_DIR/desc_by_type.csv, desc_by_month.csv, desc_by_users.csv.
"Agent users now" = different people who opened an agent pull request in the repository in the previous 30 days,
counting the author of the pull request if it is an agent pull request.
"""
import sys

import numpy as np
import pandas as pd

d = pd.read_parquet(sys.argv[1])
out = sys.argv[2]
d = d[~(d.author_is_bot & ~d.is_agent)].copy()  # drop dependabot and similar
d["type"] = np.where(d.is_agent, "agent", "no agent")
d["month"] = d.created_at.dt.strftime("%Y-%m")
done = d.created_at < pd.Timestamp("2026-10-20", tz="UTC")
has_lines = d.merged & (d.added_lines > 0) & (d.created_at < pd.Timestamp("2026-09-20", tz="UTC"))
d["merged_f"] = np.where(done, d.merged.astype(float), np.nan)
d["h"] = np.where(done, d.hours_to_merge, np.nan)
d["reverted_f"] = np.where(d.merged & done, d.reverted.astype(float), np.nan)
d["lost_any"] = np.where(has_lines, (d.lost_30d > 0).astype(float), np.nan)
d["lost_share"] = np.where(has_lines, (d.lost_30d / d.added_lines).clip(upper=1), np.nan)
d["lost_other"] = np.where(has_lines, (d.lost_30d_other > 0).astype(float), np.nan)
d["lost_other_agent"] = np.where(has_lines, (d.lost_30d_other_agent > 0).astype(float), np.nan)
d["lost_concurrent"] = np.where(has_lines, (d.lost_30d_concurrent > 0).astype(float), np.nan)
d["shared"] = np.where(d.closes_issue, d.issue_shared.astype(float), np.nan)
d["users_now"] = d.other_users_30d + (d.is_agent & d.launcher.notna()).astype(int)
d["users"] = pd.cut(d.users_now, [-1, 0, 1, 2, 4, 1e9], labels=["0", "1", "2", "3-4", "5+"])


def table(g):
    q = lambda s, p: s.quantile(p)
    return pd.Series({
        "pull requests": len(g), "repositories": g.repo.nunique(),
        "merged %": 100 * g.merged_f.mean(),
        "hours to merge p25": q(g.h, .25), "hours to merge median": q(g.h, .5), "hours to merge p75": q(g.h, .75),
        "hours to merge p90": q(g.h, .9),
        "broke main % (of those with tests)": 100 * g.broke_main.mean(), "with tests n": g.broke_main.count(),
        "reverted % (of merged)": 100 * g.reverted_f.mean(),
        "lines measured n": g.lost_any.count(), "added lines median": g.added_lines[g.lost_any.notna()].median(),
        "any line lost in 30d %": 100 * g.lost_any.mean(), "share of lines lost, mean %": 100 * g.lost_share.mean(),
        "any line lost to another person %": 100 * g.lost_other.mean(),
        "any line lost to another person's agent %": 100 * g.lost_other_agent.mean(),
        "any line lost to a concurrent pull request of another person %": 100 * g.lost_concurrent.mean(),
        "closes an issue n": g.shared.count(), "issue shared with another person % (of those)": 100 * g.shared.mean(),
        "others' agent PRs open at opening, mean": g.others_open.mean(), "none open %": 100 * (g.others_open == 0).mean()})


pd.set_option("display.width", 200, "display.max_rows", 200, "display.float_format", lambda v: f"{v:,.2f}")
t = d.groupby("type").apply(table, include_groups=False).T
t.to_csv(f"{out}/desc_by_type.csv")
print(t.to_string())
m = d.groupby(["month", "type"]).apply(table, include_groups=False).reset_index()
m.to_csv(f"{out}/desc_by_month.csv", index=False)
cols = ["pull requests", "merged %", "hours to merge median", "broke main % (of those with tests)",
        "any line lost to another person %", "none open %"]
print(m[m.type == "agent"].set_index("month")[cols].to_string())
print(m[m.type == "no agent"].set_index("month")[cols[:5]].to_string())
nu = d.groupby("month").apply(lambda g: pd.Series({"repos with agent PRs": g[g.is_agent].repo.nunique(),
     "agent users (people)": g[g.is_agent].launcher.nunique(), "agent share of PRs %": 100 * g.is_agent.mean()}), include_groups=False)
print(nu.to_string())
u = d.groupby(["type", "users"], observed=True).apply(table, include_groups=False).reset_index()
u.to_csv(f"{out}/desc_by_users.csv", index=False)
cols2 = ["pull requests", "repositories", "merged %", "hours to merge median", "broke main % (of those with tests)", "reverted % (of merged)",
         "any line lost in 30d %", "any line lost to another person %", "any line lost to a concurrent pull request of another person %",
         "issue shared with another person % (of those)"]
print(u.set_index(["type", "users"])[cols2].T.to_string())
print(d[d.is_agent].agent.value_counts().to_string())
print(d[d.is_agent].groupby("agent").apply(table, include_groups=False)[cols2[:8]].to_string())
