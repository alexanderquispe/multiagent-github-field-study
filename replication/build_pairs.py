"""Rebuild the co-active pair sample of Xu, Subramanian and Karthik (arXiv 2607.04697) from the AIDev-pop tables,
and add what their sample leaves out: the account that opened each pull request.

Usage: python build_pairs.py AIDEV_DIR OUT_CSV [--all-pairs]
  AIDEV_DIR holds pull_request.parquet and repository.parquet (AIDev revision v3 for the paper's snapshot).
  Default: their sample (one pair per repository and stratum; 625 same-agent repositories drawn with seed 42, and
  every cross-agent repository). --all-pairs writes every co-active pair of every repository instead.

Two pull requests are co-active when their open intervals overlap (created_at to closed_at, or merged_at, or the
latest date in the data if still open), as in the authors' build_sample.py.
"""
import sys

import numpy as np
import pandas as pd

src, out = sys.argv[1], sys.argv[2]
all_pairs = "--all-pairs" in sys.argv

df = pd.read_parquet(f"{src}/pull_request.parquet")
repo = pd.read_parquet(f"{src}/repository.parquet")
id2name = repo.set_index("id")["full_name"].to_dict()
for c in ("created_at", "closed_at", "merged_at"):
    df[c] = pd.to_datetime(df[c], errors="coerce", utc=True)
gmax = pd.concat([df["closed_at"], df["merged_at"], df["created_at"]]).max()
df["start"] = df["created_at"]
df["end"] = df["closed_at"].fillna(df["merged_at"]).fillna(gmax)
df = df.dropna(subset=["start"]).copy()
user = {(r, n): u for r, n, u in zip(df.repo_id, df.number, df.user)}
merged = {(r, n): pd.notna(m) for r, n, m in zip(df.repo_id, df.number, df.merged_at)}


def overlaps(rows, want_cross, first_only):
    """Sweep pull requests by start date; yield overlapping pairs of the wanted kind."""
    rows = sorted(rows, key=lambda r: r[0])
    active = []
    for s, e, ag, num in rows:
        active = [a for a in active if a[0] >= s]
        for ae, aag, anum in active:
            if (aag != ag) == want_cross:
                yield (anum, num, aag, ag)
                if first_only:
                    return
        active.append((e, ag, num))


same, cross = [], []
for rid, g in df.groupby("repo_id"):
    name = id2name.get(rid)
    if len(g) < 2 or not name:
        continue
    recs = list(zip(g["start"], g["end"], g["agent"], g["number"]))
    for a, b, aga, agb in overlaps(recs, False, not all_pairs):
        same.append(("same", name, rid, a, b, aga, agb))
    if g["agent"].nunique() >= 2:
        for a, b, aga, agb in overlaps(recs, True, not all_pairs):
            cross.append(("cross", name, rid, a, b, aga, agb))
print("repositories with a same-agent pair:", len({r[1] for r in same}), "| with a cross-agent pair:",
      len({r[1] for r in cross}))
if not all_pairs and len(same) > 625:
    idx = np.random.default_rng(42).choice(len(same), 625, replace=False)
    same = [same[i] for i in sorted(idx)]
rows = cross + same
res = pd.DataFrame(rows, columns=["stratum", "repo", "repo_id", "prA", "prB", "agentA", "agentB"])
res["userA"] = [user[(r, a)] for r, a in zip(res.repo_id, res.prA)]
res["userB"] = [user[(r, b)] for r, b in zip(res.repo_id, res.prB)]
res["mergedA"] = [merged[(r, a)] for r, a in zip(res.repo_id, res.prA)]
res["mergedB"] = [merged[(r, b)] for r, b in zip(res.repo_id, res.prB)]
res.to_csv(out, index=False)
print("pairs written:", len(res), res.stratum.value_counts().to_dict())
