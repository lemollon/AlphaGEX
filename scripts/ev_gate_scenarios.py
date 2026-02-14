#!/usr/bin/env python3
"""
Visualize how the EV gate affects trade frequency across market regimes.

Shows the full signal pipeline gate cascade and EV pass rates
for different market conditions.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent.parent / "ev_gate_scenarios.png"

# ── Theme ──────────────────────────────────────────────────────────
BG       = "#0f1117"
CARD_BG  = "#1a1d27"
TEXT     = "#e2e8f0"
MUTED    = "#94a3b8"
GREEN    = "#22c55e"
RED      = "#ef4444"
AMBER    = "#f59e0b"
BLUE     = "#3b82f6"
CYAN     = "#06b6d4"
PURPLE   = "#a855f7"
PINK     = "#ec4899"

plt.rcParams.update({
    "figure.facecolor": BG,
    "axes.facecolor": CARD_BG,
    "text.color": TEXT,
    "axes.labelcolor": TEXT,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.edgecolor": "#334155",
    "grid.color": "#1e293b",
    "font.family": "monospace",
    "font.size": 10,
})

fig = plt.figure(figsize=(20, 24))
fig.suptitle(
    "AGAPE-SPOT  EV Gate  —  Trade Frequency Impact by Market Regime",
    fontsize=18, fontweight="bold", color=CYAN, y=0.98,
)

# ═══════════════════════════════════════════════════════════════════
# CHART 1: Signal Pipeline Funnel  (top-left)
# ═══════════════════════════════════════════════════════════════════
ax1 = fig.add_axes([0.05, 0.72, 0.42, 0.22])

# Simulated pass rates per gate (% of scans that survive)
gates = [
    "Raw Scans\n(every cycle)",
    "Confidence\nFilter",
    "Funding\nData Check",
    "ETH Leader\nFilter",
    "Momentum\nFilter",
    "Choppy\nEV Gate",
    "Normal\nEV Gate",
    "Direction\nTracker",
    "TRADE\nEXECUTED",
]

# Three scenarios: trending, mild chop, heavy chop
trending  = [100, 85, 80, 75, 65, 65, 58, 52, 52]  # choppy gate N/A
mild_chop = [100, 85, 80, 75, 65, 42, 38, 34, 34]
heavy_chop= [100, 85, 80, 75, 65, 18, 16, 14, 14]

x = np.arange(len(gates))
w = 0.25

bars1 = ax1.bar(x - w, trending, w, color=GREEN, alpha=0.85, label="Trending (no choppy gate)")
bars2 = ax1.bar(x,     mild_chop, w, color=AMBER, alpha=0.85, label="Mild Chop (EV ~$0.40)")
bars3 = ax1.bar(x + w, heavy_chop, w, color=RED, alpha=0.85, label="Heavy Chop (EV ~$0.15)")

ax1.set_ylabel("% of Scans Surviving", fontsize=11)
ax1.set_title("Signal Pipeline Funnel — Gate-by-Gate Survival Rate", fontsize=13, color=TEXT, pad=12)
ax1.set_xticks(x)
ax1.set_xticklabels(gates, fontsize=7.5, ha="center")
ax1.set_ylim(0, 115)
ax1.legend(loc="upper right", fontsize=9, framealpha=0.3, edgecolor="#334155")
ax1.grid(axis="y", alpha=0.3)

# Annotate the choppy gate column
ax1.annotate(
    "CHOPPY GATE\nEV > $0.50 required",
    xy=(5, 65), xytext=(5, 100),
    fontsize=8, color=PINK, fontweight="bold", ha="center",
    arrowprops=dict(arrowstyle="->", color=PINK, lw=1.5),
)

# ═══════════════════════════════════════════════════════════════════
# CHART 2: EV Threshold Comparison  (top-right)
# ═══════════════════════════════════════════════════════════════════
ax2 = fig.add_axes([0.55, 0.72, 0.40, 0.22])

ev_values = np.linspace(-1.0, 2.0, 300)

# What fraction of signals at each EV level pass each gate?
# Normal gate: pass if EV > $0.00
normal_pass = (ev_values > 0.0).astype(float)
# Choppy gate: pass if EV > $0.50
choppy_pass = (ev_values > 0.50).astype(float)

ax2.fill_between(ev_values, normal_pass, alpha=0.3, color=GREEN, step="mid")
ax2.fill_between(ev_values, choppy_pass, alpha=0.3, color=RED, step="mid")
ax2.step(ev_values, normal_pass, color=GREEN, lw=2.5, label="Normal Gate: EV > $0.00", where="mid")
ax2.step(ev_values, choppy_pass, color=RED, lw=2.5, label="Choppy Gate: EV > $0.50", where="mid")

# Shade the "blocked only in choppy" zone
mask = (ev_values > 0.0) & (ev_values <= 0.50)
ax2.fill_between(ev_values, 0, 1, where=mask, alpha=0.15, color=AMBER,
                 label="Blocked ONLY in choppy ($0–$0.50)")

ax2.axvline(0.0, color=GREEN, ls="--", alpha=0.6, lw=1)
ax2.axvline(0.50, color=RED, ls="--", alpha=0.6, lw=1)
ax2.annotate("$0.00", xy=(0.0, 1.05), fontsize=9, color=GREEN, ha="center", fontweight="bold")
ax2.annotate("$0.50", xy=(0.50, 1.05), fontsize=9, color=RED, ha="center", fontweight="bold")

ax2.set_xlabel("Expected Value per Trade ($)", fontsize=11)
ax2.set_ylabel("Pass / Block", fontsize=11)
ax2.set_yticks([0, 1])
ax2.set_yticklabels(["BLOCKED", "PASS"], fontsize=10)
ax2.set_title("EV Threshold: Normal vs Choppy Market", fontsize=13, color=TEXT, pad=12)
ax2.legend(loc="center right", fontsize=8.5, framealpha=0.3, edgecolor="#334155")
ax2.set_xlim(-1.0, 2.0)
ax2.grid(axis="x", alpha=0.3)

# ═══════════════════════════════════════════════════════════════════
# CHART 3: Simulated Daily Trades Over 30 Days  (middle)
# ═══════════════════════════════════════════════════════════════════
ax3 = fig.add_axes([0.05, 0.42, 0.90, 0.24])

np.random.seed(42)
days = np.arange(1, 31)

# Simulate market conditions per day (0=trending, 1=mild chop, 2=heavy chop)
market_type = np.array([
    0, 0, 1, 1, 2, 0, 0, 1, 2, 2,  # days 1-10
    1, 0, 0, 0, 1, 2, 2, 1, 0, 0,  # days 11-20
    1, 2, 2, 2, 1, 0, 0, 1, 1, 0,  # days 21-30
])

# Without EV gate: ~8-12 trades/day regardless
no_gate_trades = np.random.randint(7, 13, size=30)

# With EV gate: trade count depends on market regime
with_gate_trades = np.zeros(30, dtype=int)
for i, mt in enumerate(market_type):
    if mt == 0:    # trending: ~7-11 trades (slight reduction from normal gate)
        with_gate_trades[i] = np.random.randint(7, 12)
    elif mt == 1:  # mild chop: ~3-6 trades (choppy gate cuts ~50%)
        with_gate_trades[i] = np.random.randint(3, 7)
    else:          # heavy chop: ~0-2 trades (choppy gate blocks ~85%)
        with_gate_trades[i] = np.random.randint(0, 3)

# Background shading for market regime
colors_bg = {0: GREEN, 1: AMBER, 2: RED}
for i, mt in enumerate(market_type):
    ax3.axvspan(days[i] - 0.4, days[i] + 0.4, alpha=0.08, color=colors_bg[mt])

ax3.bar(days - 0.2, no_gate_trades, 0.35, color=MUTED, alpha=0.5, label="Without EV Gate (flat ~10/day)")
ax3.bar(days + 0.2, with_gate_trades, 0.35, color=CYAN, alpha=0.85, label="With EV Gate (adaptive)")

ax3.set_xlabel("Day", fontsize=11)
ax3.set_ylabel("Trades / Day", fontsize=11)
ax3.set_title(
    "Daily Trade Count — 30-Day Simulation (background = market regime)",
    fontsize=13, color=TEXT, pad=12,
)
ax3.set_xticks(days)
ax3.set_xlim(0.2, 30.8)
ax3.set_ylim(0, 16)
ax3.legend(loc="upper right", fontsize=9.5, framealpha=0.3, edgecolor="#334155")
ax3.grid(axis="y", alpha=0.3)

# Custom legend for background colors
trend_patch = mpatches.Patch(color=GREEN, alpha=0.25, label="Trending")
mild_patch  = mpatches.Patch(color=AMBER, alpha=0.25, label="Mild Chop")
heavy_patch = mpatches.Patch(color=RED,   alpha=0.25, label="Heavy Chop")
leg2 = ax3.legend(
    handles=[trend_patch, mild_patch, heavy_patch],
    loc="upper left", fontsize=8.5, framealpha=0.3, edgecolor="#334155",
    title="Market Regime", title_fontsize=9,
)
ax3.add_artist(leg2)
# Re-add primary legend
ax3.legend(loc="upper right", fontsize=9.5, framealpha=0.3, edgecolor="#334155")

# Summary stats
total_no_gate = no_gate_trades.sum()
total_with_gate = with_gate_trades.sum()
pct_reduction = (1 - total_with_gate / total_no_gate) * 100
ax3.text(
    0.5, 0.92,
    f"30-day total:  No Gate = {total_no_gate} trades  |  With Gate = {total_with_gate} trades  |  "
    f"Reduction = {pct_reduction:.0f}%",
    transform=ax3.transAxes, fontsize=10, color=AMBER, ha="center",
    fontweight="bold",
    bbox=dict(boxstyle="round,pad=0.4", facecolor=BG, edgecolor=AMBER, alpha=0.8),
)

# ═══════════════════════════════════════════════════════════════════
# CHART 4: Cumulative P&L Comparison  (bottom-left)
# ═══════════════════════════════════════════════════════════════════
ax4 = fig.add_axes([0.05, 0.10, 0.42, 0.26])

np.random.seed(99)

# Simulate per-trade P&L across 200 scans
n_scans = 200

# No gate: takes all signals, many small losses in chop
no_gate_pnl = []
with_gate_pnl = []
scan_market = np.random.choice([0, 1, 2], size=n_scans, p=[0.4, 0.35, 0.25])

for i in range(n_scans):
    mt = scan_market[i]

    # Without gate: always trades
    if mt == 0:
        no_gate_pnl.append(np.random.choice([12, 15, 8, -6, -5, 18, -4, 10]))
    elif mt == 1:
        no_gate_pnl.append(np.random.choice([5, -8, -6, 3, -10, 2, -7, 4]))
    else:
        no_gate_pnl.append(np.random.choice([-8, -12, -5, 2, -9, -6, -4, -11]))

    # With gate: blocked in chop, trades in trend
    if mt == 0:
        with_gate_pnl.append(np.random.choice([12, 15, 8, -6, -5, 18, -4, 10]))
    elif mt == 1:
        # ~50% pass choppy gate (the ones with actual edge)
        if np.random.random() < 0.45:
            with_gate_pnl.append(np.random.choice([6, 8, 4, -3, 5, 7, -2, 3]))
        else:
            with_gate_pnl.append(0)  # blocked
    else:
        # ~15% pass heavy choppy gate
        if np.random.random() < 0.15:
            with_gate_pnl.append(np.random.choice([5, 3, -2, 4]))
        else:
            with_gate_pnl.append(0)  # blocked

cum_no_gate = np.cumsum(no_gate_pnl)
cum_with_gate = np.cumsum(with_gate_pnl)

ax4.plot(cum_no_gate, color=MUTED, alpha=0.7, lw=1.5, label=f"No EV Gate (final: ${cum_no_gate[-1]:.0f})")
ax4.plot(cum_with_gate, color=CYAN, lw=2.5, label=f"With EV Gate (final: ${cum_with_gate[-1]:.0f})")
ax4.fill_between(range(n_scans), cum_no_gate, cum_with_gate,
                 where=cum_with_gate > cum_no_gate, alpha=0.15, color=GREEN)
ax4.fill_between(range(n_scans), cum_no_gate, cum_with_gate,
                 where=cum_with_gate <= cum_no_gate, alpha=0.1, color=RED)

ax4.axhline(0, color=MUTED, ls=":", alpha=0.3)
ax4.set_xlabel("Trade Scan #", fontsize=11)
ax4.set_ylabel("Cumulative P&L ($)", fontsize=11)
ax4.set_title("Cumulative P&L — With vs Without EV Gate", fontsize=13, color=TEXT, pad=12)
ax4.legend(loc="upper left", fontsize=9, framealpha=0.3, edgecolor="#334155")
ax4.grid(alpha=0.3)

# ═══════════════════════════════════════════════════════════════════
# CHART 5: Scenario Summary Table (bottom-right)
# ═══════════════════════════════════════════════════════════════════
ax5 = fig.add_axes([0.55, 0.10, 0.40, 0.26])
ax5.axis("off")

table_data = [
    ["Metric", "Trending", "Mild Chop", "Heavy Chop"],
    ["Choppy Detected?", "NO", "YES", "YES"],
    ["Choppy EV Threshold", "N/A", "> $0.50", "> $0.50"],
    ["Normal EV Threshold", "> $0.00", "> $0.00", "> $0.00"],
    ["Typical EV Range", "$0.30–$1.50", "$0.10–$0.60", "-$0.20–$0.30"],
    ["Choppy Gate Pass %", "100% (skip)", "~45%", "~15%"],
    ["Normal Gate Pass %", "~90%", "~85%", "~80%"],
    ["Net Trade Frequency", "~8–11/day", "~3–6/day", "~0–2/day"],
    ["Frequency Change", "—", "~50% fewer", "~85% fewer"],
    ["ATR Stop Multiplier", "1.5×", "2.0×", "2.0×"],
    ["Cold Start Gate", "win_prob≥50%", "win_prob≥52%", "win_prob≥52%"],
    ["Max Positions", "2–3/ticker", "2–3/ticker", "2–3/ticker"],
]

colors_cell = []
for i, row in enumerate(table_data):
    if i == 0:
        colors_cell.append([CYAN] * 4)
    else:
        colors_cell.append([TEXT, GREEN, AMBER, RED])

table = ax5.table(
    cellText=table_data,
    cellLoc="center",
    loc="center",
    bbox=[0, 0, 1, 1],
)

table.auto_set_font_size(False)
table.set_fontsize(9.5)

for (r, c), cell in table.get_celld().items():
    cell.set_edgecolor("#334155")
    cell.set_linewidth(0.5)
    if r == 0:
        cell.set_facecolor("#1e293b")
        cell.set_text_props(fontweight="bold", color=CYAN, fontsize=10)
        cell.set_height(0.09)
    else:
        cell.set_facecolor(CARD_BG)
        cell.set_text_props(color=colors_cell[r][c])
        cell.set_height(0.08)
    if c == 0 and r > 0:
        cell.set_text_props(fontweight="bold", color=MUTED, ha="left")

ax5.set_title(
    "Scenario Summary — EV Gate Impact per Market Regime",
    fontsize=13, color=TEXT, pad=15,
)

# ── Footer ─────────────────────────────────────────────────────────
fig.text(
    0.5, 0.03,
    "Key insight: The EV gate is ADAPTIVE — it doesn't reduce frequency in trending markets.\n"
    "It only throttles when the Bayesian tracker detects your edge has disappeared in choppy conditions.\n"
    "Fewer trades in chop = fewer losses = higher net P&L.",
    ha="center", fontsize=11, color=AMBER, fontstyle="italic",
    bbox=dict(boxstyle="round,pad=0.5", facecolor=BG, edgecolor=AMBER, alpha=0.5),
)

plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"Saved to {OUT}")
