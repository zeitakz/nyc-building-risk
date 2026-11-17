"""Helpers shared by site pages: load pilot data and draw the rank chart."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path.cwd().parent / "pilot"))
import matplotlib.pyplot as plt
from pilot_stats import score, n_controls, FIRE_FEATURES, COLLAPSE_FEATURES

INK, QUIET, GRID, ACCENT, MUTED = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#a9a8a2"

def rank_chart(rows, title):
    rows = rows[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.5 * len(rows) + 1.1))
    for i, r in enumerate(rows):
        sig = r["p_value"] < 0.05
        ax.plot([0.5, r["mean_pct"]], [i, i], color=GRID, lw=2, zorder=1)
        ax.scatter(r["mean_pct"], i, s=70, color=ACCENT if sig else MUTED, zorder=3,
                   edgecolor="white", linewidth=1.5)
        p = "p < 0.01" if r["p_value"] < 0.01 else f"p = {r['p_value']:.2f}"
        ax.text(r["mean_pct"] + (0.025 if r["mean_pct"] >= 0.5 else -0.025), i,
                f"{r['mean_pct']:.0%}  ({p})", va="center",
                ha="left" if r["mean_pct"] >= 0.5 else "right", fontsize=9, color=QUIET)
    ax.axvline(0.5, color=QUIET, lw=1, ls=(0, (3, 3)), zorder=0)
    ax.text(0.515, len(rows) - 0.3, "typical for the block", fontsize=8.5, color=QUIET, ha="left")
    ax.set_yticks(range(len(rows)), [r["feature"] for r in rows], fontsize=9.5, color=INK)
    ax.set_xlim(0, 1.12); ax.set_ylim(-0.6, len(rows) - 0.1)
    ax.set_xticks([0, .25, .5, .75, 1], ["0%", "25%", "50%", "75%", "100%"], fontsize=9, color=QUIET)
    ax.set_xlabel("Average percentile rank of case buildings vs. block neighbors", fontsize=9, color=QUIET)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID); ax.tick_params(length=0)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.suptitle(title, x=0.01, ha="left", fontsize=11.5, color=INK, fontweight="semibold")
    return fig
