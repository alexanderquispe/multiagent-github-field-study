"""Figure: monthly evolution of the outcomes, agent pull requests against pull requests without an agent.

Usage: python plot_descriptives.py RESULTS_DIR   (reads desc_by_month.csv, writes desc_by_month.png)
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

R = sys.argv[1]
m = pd.read_csv(f"{R}/desc_by_month.csv")
m = m[m.month >= "2025-07"]
COL = {"agent": "#2a78d6", "no agent": "#eb6834"}
NAME = {"agent": "Con agente", "no agent": "Sin agente"}
PANELS = [("pull requests", "Pull requests abiertos por mes", None, "2026-11"),
          ("merged %", "Mergeados (%)", (60, 100), "2026-10"),
          ("hours to merge median", "Horas hasta el merge (mediana)", None, "2026-10"),
          ("broke main % (of those with tests)", "Rompió la rama principal (%, desde dic. 2025)", (0, 40), "2026-11"),
          ("any line lost to another person %", "Alguna línea borrada por otra persona en 30 días (%)", (0, 40), "2026-09"),
          ("issue shared with another person % (of those)", "Issue compartido con otra persona (%)", (0, 30), "2026-11")]
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#b5b4ae",
                     "text.color": "#0b0b0b", "axes.labelcolor": "#52514e", "xtick.color": "#52514e", "ytick.color": "#52514e"})
fig, axes = plt.subplots(3, 2, figsize=(11, 9.5), facecolor="#fcfcfb")
months = sorted(m.month.unique())
ticks = [i for i, x in enumerate(months) if x[5:] in ("01", "04", "07", "10")]
for ax, (col, title, ylim, last) in zip(axes.flat, PANELS):
    ax.set_facecolor("#fcfcfb")
    for t in ("no agent", "agent"):
        s = m[(m.type == t) & (m.month <= last)].set_index("month")[col].reindex(months)
        if col.startswith("broke"):
            s[s.index < "2025-12"] = float("nan")
        ax.plot(range(len(months)), s.values, color=COL[t], lw=2, marker="o", ms=3.5)
        v = s.dropna()
        ax.annotate(f"{NAME[t]}", (months.index(v.index[-1]), v.iloc[-1]), xytext=(6, 0), textcoords="offset points",
                    va="center", fontsize=8.5, color="#0b0b0b")
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold")
    ax.set_xticks(ticks, [months[i] for i in ticks])
    ax.set_xlim(-0.5, len(months) + 2.6)
    ax.grid(axis="y", color="#e6e5e0", lw=0.8)
    ax.set_axisbelow(True)
    if ylim:
        ax.set_ylim(*ylim)
    else:
        ax.set_ylim(bottom=0)
handles = [plt.Line2D([], [], color=COL[t], lw=2, marker="o", ms=4, label=NAME[t]) for t in ("agent", "no agent")]
fig.legend(handles=handles, loc="upper right", ncol=2, frameon=False, bbox_to_anchor=(0.98, 0.985))
fig.suptitle("234 repositorios, pull requests por mes de apertura", x=0.02, ha="left", fontsize=12, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.96))
fig.savefig(f"{R}/desc_by_month.png", dpi=150)
