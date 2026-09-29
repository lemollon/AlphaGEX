# EMBER Phase 1 — SPARK 1DTE intraday exit study

> **Historical document — superseded for Spark/Flame operations as of September 28, 2026.**
> The SPARK 1DTE iron-condor baseline is the historical study baseline, not the September 28 live EBB strategy. Preserve these measured results; do not reuse them as evidence for the current product.
> Use [Spark and Flame current state, September 28](../../../../ironforge/SPARK_FLAME_CURRENT_STATE_2026-09-28.md) for the current 0DTE EBB rules, customer sizing, feature switches, and account boundaries.
> Historical results and incident findings below retain their original scope; they are not current deployment verification.

## Historical content

- Trading days: 567
- Headline fill model: `ask_cross`

## Best policy (in-sample)
- **pt40_sl1.0_t385** — EV/contract $-6.1604, win rate 59.63%, total $-2334.8, Sharpe -0.1536, maxDD $2511.8

## SPARK live baseline (PT 30 / SL 0.5x / EOD)
- EV/contract $-9.3319, win rate 55.41%, total $-3536.8

## Out-of-sample (2025) check of the chosen policy
- EV/contract $-15.9966, win rate 47.46%, total $-2831.4
