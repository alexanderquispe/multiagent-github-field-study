"""Draw the pairs for the user-level merge replay from the full list of co-active pairs.

Usage: python sample_user_pairs.py ALL_PAIRS_CSV OUT_CSV [K]
Keeps pairs in which both pull requests were opened by a human account (so the opener is the person who launched
the agent), in repositories that have at least one different-user pair. From each such repository it draws up to K
different-user pairs and up to K same-user pairs (seed 42), so that the comparison is within repository.
"""
import sys

import pandas as pd

src, out = sys.argv[1], sys.argv[2]
k = int(sys.argv[3]) if len(sys.argv) > 3 else 10
BOTS = {"Copilot", "devin-ai-integration[bot]", "cursor[bot]"}


def is_bot(u):
    return u in BOTS or str(u).endswith("[bot]")


p = pd.read_csv(src)
p = p[~p.userA.map(is_bot) & ~p.userB.map(is_bot)].copy()
p["same_user"] = p.userA == p.userB
repos = set(p.loc[~p.same_user, "repo"])
p = p[p.repo.isin(repos)].drop_duplicates(["repo", "prA", "prB"])
parts = [g.sample(min(k, len(g)), random_state=42) for _, g in p.groupby(["repo", "same_user"])]
s = pd.concat(parts).sort_values(["repo", "same_user", "prA", "prB"])
s.to_csv(out, index=False)
print("repositories:", s.repo.nunique(), "| pairs:", len(s), s.groupby(["stratum", "same_user"]).size().to_dict())
