"""Do people who never use agents get merged less when agent pull requests fill their repository?

Usage: python crowd_out.py PR_OUTCOMES_PARQUET OUT_DIR
Sample: pull requests (2025-07 to 2026-10-19) by people with no agent pull request in that repository, ever.
Agent load, measured when the pull request is opened: share of the repository's pull requests of the previous
30 days that were agent pull requests (and, separately, how many agent and how many other pull requests).
Regressions with a fixed effect for each person in each repository and for each calendar month; standard errors
clustered by repository. Writes OUT_DIR/crowd_out.csv, crowd_out_bins.csv and crowd_out.png.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

d = pd.read_parquet(sys.argv[1])
out = sys.argv[2]
d = d[~(d.author_is_bot & ~d.is_agent)].copy()
t = d.created_at.astype("int64").to_numpy()
d["agent_30d"], d["other_30d"] = 0, 0
W = 30 * 86400 * 10**9
for repo, g in d.groupby("repo", sort=False):
    ta = np.sort(g.created_at[g.is_agent].astype("int64").to_numpy())
    to = np.sort(g.created_at[~g.is_agent].astype("int64").to_numpy())
    x = g.created_at.astype("int64").to_numpy()
    d.loc[g.index, "agent_30d"] = np.searchsorted(ta, x, "left") - np.searchsorted(ta, x - W, "left")
    d.loc[g.index, "other_30d"] = np.searchsorted(to, x, "left") - np.searchsorted(to, x - W, "left")
d["share"] = d.agent_30d / (d.agent_30d + d.other_30d).clip(lower=1)
ever = d[d.is_agent & d.launcher.notna()].groupby(["repo", "launcher"]).size()
d["person"] = d.repo + "|" + d.launcher.fillna("?")
users = set(r + "|" + l for r, l in ever.index)
s = d[~d.is_agent & d.launcher.notna() & ~d.person.isin(users)]
s = s[(s.created_at >= "2025-07-01") & (s.created_at < pd.Timestamp("2026-10-20", tz="UTC"))].copy()
s["month"] = s.created_at.dt.strftime("%Y-%m")
s["merged_f"] = s.merged.astype(float)
s["log_h"] = np.log1p(s.hours_to_merge)
s["n_person"] = s.groupby("person").person.transform("size")
s["la"], s["lo"] = np.log1p(s.agent_30d), np.log1p(s.other_30d)
BINS = [-0.01, 0, 0.10, 0.25, 0.50, 1.0]
LAB = ["0%", "1 a 10%", "10 a 25%", "25 a 50%", "más de 50%"]
s["bin"] = pd.cut(s.share, BINS, labels=LAB)
print(f"people who never use agents: {s.person.nunique()} in {s.repo.nunique()} repositories; pull requests: {len(s)}")


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
    return b, np.sqrt(np.diag(XtX @ meat @ XtX)), len(df), df.repo.nunique()


rows, bins = [], []
for b_ in LAB[1:]:
    s["b_" + b_] = (s.bin == b_).astype(float)
SAMPLES = [("everyone", s), ("regular contributors (10+ pull requests)", s[s.n_person >= 10]),
           ("occasional contributors (under 10)", s[s.n_person < 10])]
for name, df in SAMPLES:
    for y, yl in [("merged_f", "merged"), ("log_h", "log hours to merge")]:
        b, se, n, r = fit(df, y, ["share"])
        rows.append(dict(sample=name, outcome=yl, spec="agent share", term="agent share 0 to 1", coef=b[0], se=se[0], n=n, repos=r))
        b, se, n, r = fit(df, y, ["la", "lo"])
        for k, bb, ss in zip(["log agent pull requests, 30 days", "log other pull requests, 30 days"], b, se):
            rows.append(dict(sample=name, outcome=yl, spec="volumes", term=k, coef=bb, se=ss, n=n, repos=r))
        b, se, n, r = fit(df, y, ["b_" + x for x in LAB[1:]])
        bins.append(dict(sample=name, outcome=yl, bin=LAB[0], coef=0.0, se=0.0, n=int((df.bin == LAB[0]).sum())))
        for k, bb, ss in zip(LAB[1:], b, se):
            bins.append(dict(sample=name, outcome=yl, bin=k, coef=bb, se=ss, n=int((df.bin == k).sum())))
r = pd.DataFrame(rows)
bn = pd.DataFrame(bins)
r.to_csv(f"{out}/crowd_out.csv", index=False)
bn.to_csv(f"{out}/crowd_out_bins.csv", index=False)
pd.set_option("display.width", 220)
print(r.assign(t=r.coef / r.se).round(3).to_string(index=False))
raw = s.groupby("bin", observed=True).agg(n=("merged_f", "size"), merged=("merged_f", "mean"), hours=("hours_to_merge", "median"),
                                          repos=("repo", "nunique"), people=("person", "nunique"))
print(raw.round(3).to_string())
print(bn[bn["sample"] == "everyone"].round(3).to_string(index=False))

# ---- figure ----------------------------------------------------------------------------------------------------------
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#b5b4ae",
                     "text.color": "#0b0b0b", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})
BLUE, ORANGE, BG = "#2a78d6", "#eb6834", "#fcfcfb"
fig, ax = plt.subplots(2, 2, figsize=(11, 8.2), facecolor=BG)
for a_ in ax.flat:
    a_.set_facecolor(BG)
    a_.grid(axis="y", color="#e6e5e0", lw=0.8)
    a_.set_axisbelow(True)
x = np.arange(len(LAB))
a_ = ax[0, 0]
a_.bar(x, 100 * raw.merged.reindex(LAB), color=BLUE, width=0.6)
for i, v in enumerate(100 * raw.merged.reindex(LAB)):
    a_.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=8.5)
a_.set_xticks(x, LAB)
a_.set_ylim(0, 100)
a_.set_title("1. En bruto: % mergeado de quienes no usan agentes", loc="left", fontsize=10, fontweight="bold")
a_.set_xlabel("Pull requests de agentes como % del repositorio, 30 días previos")
for a_, y, title, scale, unit in [(ax[0, 1], "merged", "2. Misma persona: cambio en % mergeado", 100, "puntos"),
                                  (ax[1, 0], "log hours to merge", "3. Misma persona: cambio en horas al merge (log)", 1, "log")]:
    e = bn[(bn["sample"] == "everyone") & (bn.outcome == y)].set_index("bin").reindex(LAB)
    a_.axhline(0, color="#52514e", lw=1)
    a_.errorbar(x, scale * e.coef, yerr=1.96 * scale * e.se, fmt="o", color=BLUE, ms=6, lw=2, capsize=3)
    a_.set_xticks(x, LAB)
    a_.set_title(title, loc="left", fontsize=10, fontweight="bold")
    a_.set_xlabel("Respecto a 0% de agentes. Barras: intervalo de 95%")
a_ = ax[1, 1]
names = ["Todos", "Regulares\n(10 o más)", "Ocasionales\n(menos de 10)"]
v = r[(r.outcome == "merged") & (r.spec == "volumes")]
for j, (term, col, lab) in enumerate([("log agent pull requests, 30 days", BLUE, "Más pull requests de agentes"),
                                      ("log other pull requests, 30 days", ORANGE, "Más pull requests sin agente")]):
    e = v[v.term == term].set_index("sample").reindex([n for n, _ in SAMPLES])
    a_.errorbar(np.arange(3) + (j - 0.5) * 0.22, 100 * e.coef, yerr=196 * e.se, fmt="o", color=col, ms=6, lw=2, capsize=3, label=lab)
a_.axhline(0, color="#52514e", lw=1)
a_.set_xticks(np.arange(3), names)
a_.legend(frameon=False, loc="lower left", fontsize=8.5)
a_.set_title("4. Cambio en % mergeado al subir cada tipo de carga", loc="left", fontsize=10, fontweight="bold")
a_.set_xlabel("Puntos porcentuales por unidad de logaritmo. Barras: intervalo de 95%")
fig.suptitle("Personas que nunca usan agentes: ¿les va peor cuando el repositorio se llena de agentes?", x=0.02, ha="left",
             fontsize=12, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig(f"{out}/crowd_out.png", dpi=150)
