"""Is the 2026 rise in time to merge (and in lines deleted by others) of agent pull requests explained by
which repositories they are in, how big they are, or who opens them?

Usage: python trend_controls.py PR_OUTCOMES_PARQUET OUT_DIR
Month effects relative to January 2026, for pull requests opened January to October 2026, under growing controls:
  raw; + repository; + size (log lines changed, log files, log commits); + same person in the same repository;
  + exposure (log of other people's agent pull requests open at opening, own agent pull requests open).
Standard errors clustered by repository. Writes OUT_DIR/trend_controls.csv.
"""
import sys

import numpy as np
import pandas as pd

d = pd.read_parquet(sys.argv[1])
d = d[~(d.author_is_bot & ~d.is_agent) & d.launcher.notna()].copy()
d = d[(d.created_at >= "2026-01-01") & (d.created_at < pd.Timestamp("2026-10-20", tz="UTC"))]
d["month"] = d.created_at.dt.strftime("%m")
d["log_h"] = np.log1p(d.hours_to_merge)
d["merged_f"] = d.merged.astype(float)
ok_lines = d.merged & (d.added_lines > 0) & (d.created_at < pd.Timestamp("2026-09-20", tz="UTC"))
d["lost_other"] = np.where(ok_lines, (d.lost_30d_other > 0).astype(float), np.nan)
d["size1"] = np.log1p(d.additions + d.deletions)
d["size2"] = np.log1p(d.changed_files)
d["size3"] = np.log1p(d.n_commits)
d["exp1"] = np.log1p(d.others_open)
d["exp2"] = np.log1p(d.own_open)
d["person"] = d.repo + "|" + d.launcher
MONTHS = ["02", "03", "04", "05", "06", "07", "08", "09", "10"]
for m in MONTHS:
    d["m" + m] = (d.month == m).astype(float)
SIZE, EXPO = ["size1", "size2", "size3"], ["exp1", "exp2"]
SPECS = [("raw", None, []), ("+ repository", "repo", []), ("+ size", "repo", SIZE), ("+ same person", "person", SIZE),
         ("+ exposure", "person", SIZE + EXPO)]


def fit(df, y, fe, extra):
    df = df.dropna(subset=[y]).reset_index(drop=True)
    cols = ["m" + m for m in MONTHS if df["m" + m].sum() > 0] + extra
    Z = df[[y] + cols].to_numpy(float)
    Z = Z - (pd.DataFrame(Z).groupby(df[fe].to_numpy()).transform("mean").to_numpy() if fe else Z.mean(axis=0))
    Y, X = Z[:, 0], Z[:, 1:]
    XtX = np.linalg.pinv(X.T @ X)
    b = XtX @ X.T @ Y
    u = Y - X @ b
    meat = np.zeros((len(cols), len(cols)))
    for _, idx in df.groupby("repo").indices.items():
        v = X[idx].T @ u[idx]
        meat += np.outer(v, v)
    se = np.sqrt(np.diag(XtX @ meat @ XtX))
    return dict(zip(cols, zip(b, se))), len(df)


rows = []
for kind, sub in [("agent", d[d.is_agent]), ("no agent", d[~d.is_agent])]:
    for y, label in [("log_h", "log hours to merge"), ("lost_other", "any line deleted by another person"), ("merged_f", "merged")]:
        for spec, fe, extra in SPECS:
            res, n = fit(sub, y, fe, extra)
            for k, (b, se) in res.items():
                rows.append(dict(type=kind, outcome=label, spec=spec, term=k, coef=b, se=se, n=n))
r = pd.DataFrame(rows)
r.to_csv(f"{sys.argv[2]}/trend_controls.csv", index=False)
pd.set_option("display.width", 220)
order = [s[0] for s in SPECS]
for y in r.outcome.unique():
    for kind in ("agent", "no agent"):
        x = r[(r.outcome == y) & (r.type == kind)]
        t = x[x.term.isin(["m04", "m07", "m09", "m10"])].pivot(index="spec", columns="term", values="coef").reindex(order)
        s = x[x.term.isin(["m04", "m07", "m09", "m10"])].pivot(index="spec", columns="term", values="se").reindex(order)
        print(f"\n{y} | {kind} | n={x.n.iloc[0]}  (month effect vs January; standard error)")
        print(pd.DataFrame({c: [f"{a:+.3f} ({b:.3f})" for a, b in zip(t[c], s[c])] for c in t.columns}, index=order).to_string())
        e = x[(x.spec == "+ exposure") & x.term.isin(EXPO + SIZE)]
        print("   controls in last spec:", "; ".join(f"{k} {b:+.3f} ({se:.3f})" for k, b, se in zip(e.term, e.coef, e.se)))
