"""Choose the repositories to extract: a 2x2 of agent users (1 vs 2 to 4) by agent companies (one vs several).

Usage: python select_repos.py AIDEV_V5_DIR OUT_CSV [PER_CELL]
Window: pull requests opened 2025-10-01 to 2026-03-31. A repository needs at least 10 agent pull requests in the window.
"Users" are the human accounts that opened agent pull requests (Claude Code, Codex, Cursor); Copilot, Devin and Jules
pull requests are opened by a bot account, so their launcher is unknown here (column bot_share).
"""
import sys

import pandas as pd

src, out = sys.argv[1], sys.argv[2]
per_cell = int(sys.argv[3]) if len(sys.argv) > 3 else 60
p = pd.read_parquet(f"{src}/pull_request.parquet", columns=["agent", "user", "created_at", "merged_at", "repo_id"])
r = pd.read_parquet(f"{src}/repository.parquet")
p = p[p.created_at >= "2025-10-01"].copy()
p["bot"] = p.user.str.endswith("[bot]") | (p.user == "Copilot")
g = p.groupby("repo_id").agg(agent_prs=("agent", "size"), companies=("agent", "nunique"), bot_share=("bot", "mean"),
                             merged=("merged_at", lambda s: s.notna().mean()),
                             products=("agent", lambda s: "+".join(sorted(s.unique()))))
h = p[~p.bot]
g["users"] = h.groupby("repo_id").user.nunique().reindex(g.index).fillna(0).astype(int)
# how many different main products the human users have (1 = everybody uses the same one)
main = h.groupby(["repo_id", "user"]).agent.agg(lambda s: s.mode().iat[0]).reset_index()
g["user_main_products"] = main.groupby("repo_id").agent.nunique().reindex(g.index).fillna(0).astype(int)
g = g[(g.agent_prs >= 10) & g.users.between(1, 4)].copy()
g["cell_users"] = g.users.map(lambda u: "1" if u == 1 else "2-4")
g["cell_companies"] = g.companies.map(lambda c: "one" if c == 1 else "several")
g = g.join(r.set_index("id")[["full_name", "stars", "language", "is_forked"]], how="inner")
g = g[~g.is_forked]
print(pd.crosstab(g.cell_users, g.cell_companies))
print(g[g.cell_companies == "one"].groupby(["cell_users", "products"]).size())
print(g[g.cell_companies == "several"].groupby("cell_users")[["bot_share", "user_main_products"]].describe().T)
s = g.groupby(["cell_users", "cell_companies"]).sample(n=per_cell, random_state=42)
s.reset_index(names="repo_id").to_csv(out, index=False)
print(s.groupby(["cell_users", "cell_companies"])[["agent_prs", "stars", "users", "bot_share"]].median())
print("wrote", len(s), out)
