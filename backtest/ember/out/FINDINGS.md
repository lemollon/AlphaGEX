# EMBER Phase 1 — Findings: SPARK 1DTE intraday exit study

**Date:** 2026-05-21
**Sample:** 567 1DTE SPY trading days, 2023-01-03 → 2025-12-05 (`helios_options_intraday` minute bid/ask)
**Method:** one representative iron condor per day (~16Δ shorts, $5 wings, 10:00 ET entry), swept against 101 exit policies (PT × SL × time-stop) + SPARK's live baseline. Walk-forward: train 2023–24, OOS 2025 held out. Engine: `backtest/ember/`.

## Verdict: NO-GO on the strategy (engine SUCCESS)

The best policy is the **same under all three fill models** — **`pt40_sl1.0_t385`** (take profit at 40% of credit, stop at 1.0× credit, force-close 15:55 ET):

| Fill model | Best in-sample EV/ct | Best WR | SPARK baseline EV/ct | Best policy OOS-2025 EV/ct |
|---|---|---|---|---|
| mid (optimistic ceiling) | **−$4.13** | 61.7% | −$7.06 | −$11.27 |
| ask-cross (realistic floor) | **−$6.16** | 59.6% | −$9.33 | −$15.99 |
| mid + $0.03/leg slippage | −$16.68 | 43.5% | −$18.72 | −$22.23 |

> Real SPY 1DTE quotes in the data are tight — half-spread typically < $0.03/leg — so ask-cross (which pays the *actual* spread) is cheaper than the flat-$0.03 `mid_slip`. The realistic band is **mid → ask-cross ≈ −$4 to −$6/contract**; `mid_slip` overstates costs and is shown only as a stress bound.

### Three conclusions
1. **Negative EV everywhere.** 0 of 101 policies are positive in-sample under any fill. The representative 1DTE SPY iron condor loses money after costs across the full 567-day sample.
2. **Exit tuning helps but cannot fix it.** Widening SPARK's tight 0.5× stop to 1.0× and capping the day at 15:55 ET cuts the loss ~$3/contract vs SPARK's live config — but "better" is still "loses less."
3. **The in-sample edge does not generalize.** The chosen policy degrades materially out-of-sample (2025) under every fill (e.g. mid −$4.13 → −$11.27 OOS). That is overfit / regime shift, not a durable edge.

### What it means for live SPARK
SPARK's current **PT 30 / SL 0.5×** is the *worst* config in the sweep. If SPARK keeps trading 1DTE ICs, **SL 0.5×→1.0× plus a 15:55 ET hard close** is the least-bad exit and would have saved ~$3/contract over this sample. But the honest read is that the structure itself is negative-EV here, consistent with the known ceiling on 1DTE SPY premium strategies (need very high WR to overcome the payoff geometry; this runs ~55–62% WR).

### Scope / caveat
This is the **representative** IC (delta-selected ~16Δ shorts, fixed $5 wings, 10:00 ET entry). Live SPARK selects strikes off GEX walls with its own entry timing; a faithful-SPARK adapter (Phase 4) could shift the numbers. The signal here — negative across all fills *and* degrading out-of-sample — is strong enough to caution against expecting exit-tuning alone to make SPARK profitable. Also note: this models same-day exits of the 1DTE position (no 0DTE/expiry-day data), which is what SPARK actually does (79/80 live closes same-day).

### Engine status: SUCCESS
A strategy NO-GO is a successful Phase 1 — the EMBER engine is built, two-stage reviewed, validated against the live production DB, and reusable for BLAZE and faithful-SPARK adapters (Phase 4) with zero engine changes. The deliverable is the engine + this defensible, OOS-checked answer.

## Reproduce
```bash
PYTHONUTF8=1 python -m backtest.ember --start 2023-01-03 --end 2025-12-05 --fill ask_cross --out backtest/ember/out/full
# also --fill mid  and  --fill mid_slip   (PYTHONUTF8=1 required on Windows: repo config.py prints emoji that crash cp1252)
```
Per-run artifacts in `full/`, `full_mid/`, `full_slip/`: `report.md`, `summary.csv` (101-policy table), `trades.csv` (per-trade audit, git-ignored — regenerate via the command above).
