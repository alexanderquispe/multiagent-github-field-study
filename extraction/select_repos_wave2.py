"""Second sample: 2,000 repositories not in the first sample, with every many-user repository included.

Usage: python select_repos_wave2.py AIDEV_V5_DIR FIRST_SAMPLE_CSV OUT_CSV [TOTAL]
Same eligibility as select_repos.py (pull requests opened 2025-10-01 to 2026-03-31, at least 10 agent pull requests,
not a fork, at least one human account opening agent pull requests), but any number of users. All eligible
repositories with 5 or more agent users are taken; the rest of the quota is a random draw (seed 43) of the others.
"""
import sys

import pandas as pd

src, first, out = sys.argv[1], sys.argv[2], sys.argv[3]
total = int(sys.argv[4]) if len(sys.argv) > 4 else 2000
p = pd.read_parquet(f"{src}/pull_request.parquet", columns=["agent", "user", "created_at", "merged_at", "repo_id"])
r = pd.read_parquet(f"{src}/repository.parquet")
p = p[p.created_at >= "2025-10-01"].copy()
p["bot"] = p.user.str.endswith("[bot]") | (p.user == "Copilot")
g = p.groupby("repo_id").agg(agent_prs=("agent", "size"), companies=("agent", "nunique"), bot_share=("bot", "mean"),
                             products=("agent", lambda s: "+".join(sorted(s.unique()))))
g["users"] = p[~p.bot].groupby("repo_id").user.nunique().reindex(g.index).fillna(0).astype(int)
g = g[(g.agent_prs >= 10) & (g.users >= 1)].join(r.set_index("id")[["full_name", "stars", "language", "is_forked"]], how="inner")
g = g[~g.is_forked & ~g.full_name.isin(pd.read_csv(first).full_name)]
g["cell_users"] = pd.cut(g.users, [0, 1, 4, 1e9], labels=["1", "2-4", "5+"]).astype(str)
g["cell_companies"] = g.companies.map(lambda c: "one" if c == 1 else "several")
many = g[g.users >= 5]
rest = g[g.users < 5].sample(n=min(total - len(many), (g.users < 5).sum()), random_state=43)
s = pd.concat([many, rest]).reset_index(names="repo_id")
s.to_csv(out, index=False)
print("eligible and not in the first sample:", len(g), "| taken:", len(s))
print(pd.crosstab(s.cell_users, s.cell_companies, margins=True))
print(s[["agent_prs", "stars", "users"]].describe().round(0).loc[["50%", "max"]])
