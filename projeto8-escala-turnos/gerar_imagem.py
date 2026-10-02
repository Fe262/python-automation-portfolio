"""Draws imagens/escala.png from the solver's real output on the sample team (for the README)."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from escala import DAYS, SHIFTS, exemplo, resolver

emp, need = exemplo()
r = resolver(emp, need)
cores = ["#cfe8e4", "#ffe9b8", "#d9d6f2", "#f9d3d3", "#d3e6f9", "#e3f2c9", "#f5d9ec", "#e6e6e6"]
cor = {e.name: cores[i] for i, e in enumerate(emp)}

fig = plt.figure(figsize=(12.5, 5.6), dpi=130)
gs = fig.add_gridspec(1, 2, width_ratios=[2.3, 1])
ax = fig.add_subplot(gs[0])
ax.axis("off")
ax.set_title(f"Weekly schedule ({r.status}, {r.preference_misses} preferred days off missed)",
             loc="left", fontsize=11, fontweight="bold", color="#1F4E78")
cells = [[", ".join(r.schedule.get((d, s), [])) or "-" for s in range(3)] for d in range(7)]
t = ax.table(cellText=cells, rowLabels=DAYS, colLabels=SHIFTS, loc="upper center", cellLoc="center")
t.auto_set_font_size(False)
t.set_fontsize(8.5)
t.scale(1, 2.0)
for (i, j), c in t.get_celld().items():
    c.set_edgecolor("#d9d9d9")
    if i == 0:
        c.set_facecolor("#1F4E78")
        c.get_text().set_color("white")
        c.get_text().set_weight("bold")
bx = fig.add_subplot(gs[1])
nomes = list(r.shifts_per_person)
bx.barh(nomes, [r.shifts_per_person[n] for n in nomes], color=[cor[n] for n in nomes], edgecolor="#888")
bx.invert_yaxis()
bx.set_title("Shifts per person", loc="left", fontsize=11, fontweight="bold", color="#1F4E78")
bx.set_xlim(0, 6)
for i, n in enumerate(nomes):
    bx.text(r.shifts_per_person[n] + 0.1, i, str(r.shifts_per_person[n]), va="center", fontsize=9)
for s in ("top", "right"):
    bx.spines[s].set_visible(False)
fig.tight_layout()
out = Path(__file__).parent / "imagens"
out.mkdir(exist_ok=True)
fig.savefig(out / "escala.png", bbox_inches="tight")
print("ok")
