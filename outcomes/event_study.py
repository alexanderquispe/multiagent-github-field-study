"""Event study: what changes in a repository when a second person starts using a coding agent there.

Usage: python event_study.py PR_OUTCOMES_PARQUET OUT_DIR [--min-prs 1] [--pre 3] [--post 5]
Event: the month of the first agent pull request by a second launcher (with --min-prs K, a second launcher who ends
up with at least K agent pull requests). Before the event the repository has exactly one agent user (the incumbent),
so the comparison is "one agent user" against "two or more", not "no agents" against "agents".
Design: stacked difference-in-differences. For each event month g, treated repositories are those whose event is in
g; controls are repositories that already have their first agent user and get no second one until after g+POST
(or never). Months g-PRE..g+POST, only months from the first agent pull request on. Fixed effects for repository and
for calendar month within each stack; standard errors clustered by repository. Reference month: g-1.
Outcomes are monthly means over pull requests opened in the month (incumbent's agent pull requests, or pull requests
of people without agents). Writes OUT_DIR/event_study_coefs.csv and event_study_pooled.csv.
With --split, scarcity is measured in the three months before the event month (never after) and repositories are
divided at the median: load = pull requests opened per person who merges; backlog = pull requests open at the start
of the event month per pull request merged in a month; slow = median hours to merge.
"""
import argparse

import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("parquet")
ap.add_argument("out_dir")
ap.add_argument("--min-prs", type=int, default=1)
ap.add_argument("--kth", type=int, default=2, help="event = arrival of the k-th agent user; incumbents = the first k-1")
ap.add_argument("--pre", type=int, default=3)
ap.add_argument("--post", type=int, default=5)
ap.add_argument("--split", choices=["load", "backlog", "slow"], help="also estimate separately by scarcity")
a = ap.parse_args()
LAST = pd.Timestamp("2026-10-20", tz="UTC")  # pull requests opened later have had under a month to be resolved

d = pd.read_parquet(a.parquet)
d = d[d.created_at < LAST].copy()
d["m"] = d.created_at.dt.year * 12 + d.created_at.dt.month
ag = d[d.is_agent & d.launcher.notna()].sort_values("created_at")
n_by = ag.groupby(["repo", "launcher"]).size()
ev = {}
for repo, g in ag.groupby("repo"):
    first = g.drop_duplicates("launcher")
    k = a.kth
    if len(first) < k - 1:
        continue
    L1, m1 = frozenset(first.launcher.iloc[:k - 1]), first.m.iloc[k - 2]
    later = [m for m, l in zip(first.m.iloc[k - 1:], first.launcher.iloc[k - 1:]) if n_by[(repo, l)] >= a.min_prs]
    ev[repo] = (L1, m1, later[0] if later else None)

# ---- monthly outcomes ------------------------------------------------------------------------------------------------
d["is_inc"] = [r in ev and l in ev[r][0] for r, l in zip(d.repo, d.launcher)]
d["merged_f"] = d.merged.astype(float)
d["log_h"] = np.log1p(d.hours_to_merge)
d["lost_other"] = np.where(d.merged & (d.added_lines > 0), (d.lost_30d_other > 0).astype(float), np.nan)
d["lost_share"] = np.where(d.merged & (d.added_lines > 0), (d.lost_30d / d.added_lines).clip(upper=1), np.nan)
d.loc[d.created_at >= LAST - pd.Timedelta(days=30), ["lost_other", "lost_share"]] = np.nan
inc = d[d.is_agent & d.is_inc]
hum = d[~d.is_agent & ~d.author_is_bot & d.launcher.notna() & ~d.is_inc]


def monthly(x, prefix):
    g = x.groupby(["repo", "m"])
    return pd.DataFrame({f"{prefix}_n": g.size(), f"{prefix}_merged": g.merged_f.mean(), f"{prefix}_log_hours": g.log_h.mean(),
                         f"{prefix}_broke_main": g.broke_main.mean(), f"{prefix}_lost_other": g.lost_other.mean(),
                         f"{prefix}_lost_share": g.lost_share.mean()})


panel = monthly(inc, "inc").join(monthly(hum, "hum"), how="outer").reset_index()
for p in ("inc", "hum"):
    panel[f"{p}_log_n"] = np.log1p(panel[f"{p}_n"].fillna(0))
OUTCOMES = [("inc_merged", "Incumbent: share merged"), ("inc_log_hours", "Incumbent: log hours to merge"),
            ("inc_broke_main", "Incumbent: broke the main branch"), ("inc_lost_other", "Incumbent: lines deleted by someone else"),
            ("inc_lost_share", "Incumbent: share of lines deleted in 30 days"), ("inc_log_n", "Incumbent: log pull requests"),
            ("hum_merged", "People without agents: share merged"), ("hum_log_hours", "People without agents: log hours to merge"),
            ("hum_broke_main", "People without agents: broke the main branch"), ("hum_log_n", "People without agents: log pull requests")]

# ---- stacks ----------------------------------------------------------------------------------------------------------
last_m = int(d.m.max())
stacks = []
for g in sorted({e[2] for e in ev.values() if e[2] is not None}):
    if g + 1 > last_m:
        continue
    for repo, (L1, m1, m2) in ev.items():
        treated = m2 == g
        control = (m2 is None or m2 > g + a.post) and m1 <= g - 1
        if not (treated or control) or (treated and m1 > g - 1):
            continue
        for m in range(max(g - a.pre, m1), min(g + a.post, last_m) + 1):
            stacks.append((g, repo, m, int(treated), m - g))
s = pd.DataFrame(stacks, columns=["g", "repo", "m", "treated", "e"]).merge(panel, on=["repo", "m"], how="left")
s[["inc_log_n", "hum_log_n"]] = s[["inc_log_n", "hum_log_n"]].fillna(0)
print(f"second user = at least {a.min_prs} agent pull request(s) | stacks: {s.g.nunique()} | treated repositories: "
      f"{s[s.treated == 1].repo.nunique()} | control repositories: {s[s.treated == 0].repo.nunique()} | rows: {len(s)}")


def fit(df, y, cols):
    """OLS of y on cols with stack-by-repository and stack-by-month fixed effects; errors clustered by repository."""
    df = df.dropna(subset=[y]).copy()
    f1 = df.g.astype(str) + "|" + df.repo
    f2 = df.g.astype(str) + "|" + df.m.astype(str)
    Z = df[[y] + cols].to_numpy(float)
    for _ in range(200):
        before = Z.copy()
        for f in (f1, f2):
            Z = Z - pd.DataFrame(Z).groupby(f.to_numpy()).transform("mean").to_numpy()
        if np.abs(Z - before).max() < 1e-10:
            break
    Y, X = Z[:, 0], Z[:, 1:]
    keep = X.std(axis=0) > 1e-9
    b = np.full(len(cols), np.nan)
    se = np.full(len(cols), np.nan)
    if keep.sum() == 0:
        return b, se, len(df), 0
    Xk = X[:, keep]
    XtX = np.linalg.pinv(Xk.T @ Xk)
    bk = XtX @ Xk.T @ Y
    u = Y - Xk @ bk
    meat = np.zeros((Xk.shape[1], Xk.shape[1]))
    for _, idx in df.reset_index(drop=True).groupby("repo").indices.items():
        v = Xk[idx].T @ u[idx]
        meat += np.outer(v, v)
    G = df.repo.nunique()
    V = XtX @ meat @ XtX * G / (G - 1)
    b[keep], se[keep] = bk, np.sqrt(np.diag(V))
    return b, se, len(df), df[df.treated == 1].repo.nunique()


coefs, pooled = [], []
times = [e for e in range(-a.pre, a.post + 1) if e != -1]
for e in times:
    s[f"e{e}"] = ((s.treated == 1) & (s.e == e)).astype(float)
s["post"] = ((s.treated == 1) & (s.e >= 0)).astype(float)
for y, label in OUTCOMES:
    b, se, n, nt = fit(s, y, [f"e{e}" for e in times])
    for e, bb, ss in zip(times, b, se):
        coefs.append(dict(outcome=y, label=label, e=e, coef=bb, se=ss, n=n, treated_repos=nt))
    coefs.append(dict(outcome=y, label=label, e=-1, coef=0.0, se=0.0, n=n, treated_repos=nt))
    b, se, n, nt = fit(s, y, ["post"])
    pre_mean = s[(s.treated == 1) & (s.e < 0)][y].mean()
    pooled.append(dict(outcome=y, label=label, coef=b[0], se=se[0], pre_mean=pre_mean, n=n, treated_repos=nt))
tag = f"min{a.min_prs}" + (f"_k{a.kth}" if a.kth != 2 else "")
pd.DataFrame(coefs).sort_values(["outcome", "e"]).to_csv(f"{a.out_dir}/event_study_coefs_{tag}.csv", index=False)
p = pd.DataFrame(pooled)
p.to_csv(f"{a.out_dir}/event_study_pooled_{tag}.csv", index=False)
print(p.assign(t=p.coef / p.se).round(3).to_string(index=False))
c = pd.DataFrame(coefs)
print(c.pivot(index="label", columns="e", values="coef").round(3).to_string())

# ---- split by scarcity, measured before the event ---------------------------------------------------------------------
if a.split:
    people = d[~d.author_is_bot]
    rows = []
    month_start = lambda m: pd.Timestamp(year=(m - 1) // 12, month=(m - 1) % 12 + 1, day=1, tz="UTC")
    by_repo = {r: x for r, x in people.groupby("repo")}
    for (g, repo), _ in s.groupby(["g", "repo"]):
        x = by_repo.get(repo)
        if x is None:
            continue
        pre = x[(x.m >= g - 3) & (x.m <= g - 1)]
        merged_pre = x[x.merged & (x.merged_at >= month_start(g - 3)) & (x.merged_at < month_start(g))]
        t0 = month_start(g)
        open_now = ((x.created_at < t0) & (x.closed_at.isna() | (x.closed_at >= t0))).sum()
        mergers = merged_pre.merged_by.nunique()
        rows.append(dict(g=g, repo=repo, load=len(pre) / mergers if mergers else np.nan,
                         backlog=open_now / (len(merged_pre) / 3) if len(merged_pre) else np.nan,
                         slow=pre.hours_to_merge.median(), mergers=mergers, opened=len(pre) / 3))
    sc = pd.DataFrame(rows)
    cut = sc[a.split].median()
    sc["scarce"] = np.where(sc[a.split].isna(), np.nan, (sc[a.split] > cut).astype(float))
    s2 = s.merge(sc[["g", "repo", "scarce", "mergers", "opened", a.split]], on=["g", "repo"]).dropna(subset=["scarce"])
    u = s2.drop_duplicates(["g", "repo"])
    print(f"\nSplit by {a.split}: median {cut:.2f}. Units (treated, control): scarce "
          f"{int(((u.scarce == 1) & (u.treated == 1)).sum())}, {int(((u.scarce == 1) & (u.treated == 0)).sum())}; "
          f"not scarce {int(((u.scarce == 0) & (u.treated == 1)).sum())}, {int(((u.scarce == 0) & (u.treated == 0)).sum())}")
    print(u.groupby("scarce")[["mergers", "opened", a.split]].median().round(2).to_string())
    out = []
    for y, label in OUTCOMES:
        b0, se0, n0, t0_ = fit(s2[s2.scarce == 0], y, ["post"])
        b1, se1, n1, t1_ = fit(s2[s2.scarce == 1], y, ["post"])
        # difference of the two separate estimates (each half has its own controls and month effects)
        diff, sed = b1[0] - b0[0], float(np.hypot(se0[0], se1[0]))
        out.append(dict(label=label, not_scarce=b0[0], se0=se0[0], repos0=t0_, scarce=b1[0], se1=se1[0], repos1=t1_,
                        difference=diff, se_diff=sed, t=diff / sed))
    o = pd.DataFrame(out)
    o.to_csv(f"{a.out_dir}/event_study_split_{a.split}_{tag}.csv", index=False)
    print(o.round(3).to_string(index=False))
