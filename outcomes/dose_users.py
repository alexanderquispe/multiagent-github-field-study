"""Dose-response: outcomes of agent pull requests by how many people are using agents in the repository at that time.

Usage: python dose_users.py PR_OUTCOMES_PARQUET OUT_DIR
Agent users now = different people with an agent pull request in the repository in the previous 30 days, counting
the author. Left: raw means. Right: the same person in the same repository, net of calendar month, relative to
moments when that person is the only agent user. Standard errors clustered by repository.
Writes OUT_DIR/dose_users.csv and dose_users.png.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

d = pd.read_parquet(sys.argv[1])
out = sys.argv[2]
d = d[d.is_agent & d.launcher.notna() & (d.created_at >= "2025-07-01") & (d.created_at < pd.Timestamp("2026-10-20", tz="UTC"))].copy()
d["person"] = d.repo + "|" + d.launcher
d["month"] = d.created_at.dt.strftime("%Y-%m")
d["k"] = d.other_users_30d + 1
LAB = ["1", "2", "3", "4", "5 a 7", "8 o más"]
d["bin"] = pd.cut(d.k, [0, 1, 2, 3, 4, 7, 1e9], labels=LAB)
d["merged_f"] = d.merged.astype(float)
d["log_h"] = np.log1p(d.hours_to_merge)
ok = d.merged & (d.added_lines > 0) & (d.created_at < pd.Timestamp("2026-09-20", tz="UTC"))
d["lost_other"] = np.where(ok, (d.lost_30d_other > 0).astype(float), np.nan)
for b in LAB[1:]:
    d["b_" + b] = (d.bin == b).astype(float)
OUT = [("merged_f", "Mergeado (%)", 100), ("log_h", "Horas al merge (log)", 1), ("broke_main", "Rompió la rama principal (%)", 100),
       ("lost_other", "Alguna línea borrada por otra persona (%)", 100)]


def fit(df, y, cols, fes=("person", "month")):
    df = df.dropna(subset=[y]).reset_index(drop=True)
    Z = df[[y] + cols].to_numpy(float)
    for _ in range(300):
        before = Z.copy()
        for f in fes:
            Z = Z - pd.DataFrame(Z).groupby(df[f].to_numpy()).transform("mean").to_numpy()
        if np.abs(Z - before).max() < 1e-9:
            break
    Y, X = Z[:, 0], Z[:, 1:]
    XtX = np.linalg.pinv(X.T @ X)
    b = XtX @ X.T @ Y
    u = Y - X @ b
    meat = np.zeros((len(cols), len(cols)))
    for _, idx in df.groupby("repo").indices.items():
        v = X[idx].T @ u[idx]
        meat += np.outer(v, v)
    return b, np.sqrt(np.diag(XtX @ meat @ XtX)), len(df)


rows = []
for y, label, sc in OUT:
    raw = d.groupby("bin", observed=True)[y].agg(["mean", "count"]).reindex(LAB)
    b, se, n = fit(d, y, ["b_" + x for x in LAB[1:]])
    # how many people are observed both alone and in each bin (they identify the within-person estimate)
    alone = set(d[(d.bin == "1") & d[y].notna()].person)
    for i, lab in enumerate(LAB):
        both = d[(d.bin == lab) & d[y].notna() & d.person.isin(alone)].person.nunique()
        rows.append(dict(outcome=label, users=lab, raw=sc * raw["mean"][lab], n=int(raw["count"][lab]),
                         within=0.0 if i == 0 else sc * b[i - 1], se=0.0 if i == 0 else sc * se[i - 1], people_also_alone=both))
r = pd.DataFrame(rows)
r.to_csv(f"{out}/dose_users.csv", index=False)
pd.set_option("display.width", 200)
print(r.round(2).to_string(index=False))
print(d.groupby("bin", observed=True).agg(prs=("k", "size"), repos=("repo", "nunique"), people=("person", "nunique")).to_string())

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#b5b4ae",
                     "text.color": "#0b0b0b", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})
BLUE, BG = "#2a78d6", "#fcfcfb"
fig, ax = plt.subplots(4, 2, figsize=(11, 12.5), facecolor=BG)
x = np.arange(len(LAB))
for i, (y, label, sc) in enumerate(OUT):
    e = r[r.outcome == label].set_index("users").reindex(LAB)
    a0, a1 = ax[i]
    for a_ in (a0, a1):
        a_.set_facecolor(BG)
        a_.grid(axis="y", color="#e6e5e0", lw=0.8)
        a_.set_axisbelow(True)
        a_.set_xticks(x, LAB)
    a0.bar(x, e.raw, color=BLUE, width=0.6)
    for j, v in enumerate(e.raw):
        a0.text(j, v + 0.02 * e.raw.max(), f"{v:.1f}", ha="center", fontsize=8.5)
    a0.set_ylim(0, e.raw.max() * 1.15)
    a0.set_title(f"{label}: en bruto", loc="left", fontsize=10, fontweight="bold")
    a1.axhline(0, color="#52514e", lw=1)
    a1.errorbar(x, e.within, yerr=1.96 * e.se, fmt="o", color=BLUE, ms=6, lw=2, capsize=3)
    a1.set_title(f"{label}: misma persona", loc="left", fontsize=10, fontweight="bold")
ax[3, 0].set_xlabel("Personas usando agentes en el repositorio (30 días previos, contando al autor)")
ax[3, 1].set_xlabel("Cambio respecto a cuando esa persona es la única con agente. Barras: intervalo de 95%")
fig.suptitle("Pull requests con agente según cuántas personas usan agentes en el repositorio", x=0.02, ha="left", fontsize=12, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(f"{out}/dose_users.png", dpi=150)
