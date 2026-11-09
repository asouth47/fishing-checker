"""
Draws the daily tide chart in the same style as the Tide Watch page:
teal tide curve with a light fill, shaded fishing windows, labelled highs and
lows, darker shading before sunrise and after sunset.
"""

from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SEA = "#0e7a72"
SEA_FILL = (14 / 255, 122 / 255, 114 / 255, 0.13)
WINDOW = (14 / 255, 122 / 255, 114 / 255, 0.10)
NIGHT = (15 / 255, 43 / 255, 48 / 255, 0.07)
INK = "#0f2b30"
MUTED = "#55706c"
GRID = "#d8ddd2"
BG = "#ffffff"
OTHER = "#9fb3ae"


def smooth(times, values, steps=6):
    """Catmull-Rom spline through hourly points so the curve isn't jagged."""
    out_t, out_v = [], []
    n = len(values)
    for i in range(n - 1):
        p0 = values[max(i - 1, 0)]
        p1, p2 = values[i], values[i + 1]
        p3 = values[min(i + 2, n - 1)]
        for s in range(steps):
            u = s / steps
            v = 0.5 * ((2 * p1) + (-p0 + p2) * u
                       + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)
            out_t.append(times[i] + (times[i + 1] - times[i]) * u)
            out_v.append(v)
    out_t.append(times[-1])
    out_v.append(values[-1])
    return out_t, out_v


def draw(results, best, day, path):
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)

    fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=150)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # Night shading.
    if best["sunrise"]:
        ax.axvspan(start, best["sunrise"], color=NIGHT, lw=0)
        ax.axvspan(best["sunset"], end, color=NIGHT, lw=0)

    # Best fishing windows.
    for ws, we in best["window_spans"]:
        ax.axvspan(ws, we, color=WINDOW, lw=0)

    # Other spots as faint lines for comparison.
    for r in results:
        if r is best or not r["series"][0]:
            continue
        t, v = smooth(*r["series"])
        ax.plot(t, v, color=OTHER, lw=1, alpha=0.8)

    # Main curve.
    t, v = smooth(*best["series"])
    ax.fill_between(t, v, min(v) - 1.4, color=SEA_FILL, lw=0)
    ax.plot(t, v, color=SEA, lw=2.2)

    # Label highs and lows.
    for tt, kind, h in best["turns"]:
        ax.plot([tt], [h], "o", ms=5, color=SEA, mec=BG, mew=1.5, zorder=5)
        dy = 10 if kind == "High" else -16
        ax.annotate(f"{tt:%H:%M}  {h:.1f} m", (tt, h), textcoords="offset points",
                    xytext=(0, dy), ha="center", fontsize=8, color=INK,
                    family="monospace",
                    bbox=dict(boxstyle="round,pad=0.15", fc=BG, ec="none", alpha=0.85))

    ax.set_xlim(start, end)
    lo = min(v)
    hi = max(v)
    ax.set_ylim(lo - 1.4, hi + 1.0)
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f"{y:.0f} m"))
    ax.grid(True, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)

    ax.set_title(f"{best['name']}  ·  {day:%a %d %b}", loc="left",
                 fontsize=10, color=INK, fontweight="bold")
    ax.text(1.0, 1.02, "shaded = best windows   grey = other spots",
            transform=ax.transAxes, ha="right", fontsize=7, color=MUTED)

    fig.tight_layout()
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
