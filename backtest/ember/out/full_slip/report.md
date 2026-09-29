# EMBER Phase 1 — SPARK 1DTE intraday exit study

> **Historical document — superseded for Spark/Flame operations as of September 28, 2026.**
> The SPARK 1DTE iron-condor baseline is the historical study baseline, not the September 28 live EBB strategy. Preserve these measured results; do not reuse them as evidence for the current product.
> Use [Spark and Flame current state, September 28](../../../../ironforge/SPARK_FLAME_CURRENT_STATE_2026-09-28.md) for the current 0DTE EBB rules, customer sizing, feature switches, and account boundaries.
> Historical results and incident findings below retain their original scope; they are not current deployment verification.

## Historical content

- Trading days: 567
- Headline fill model: `mid_slip`

## Best policy (in-sample)
- **pt40_sl1.0_t385** — EV/contract $-16.6802, win rate 43.54%, total $-6321.8, Sharpe -0.4112, maxDD $6420.7

## SPARK live baseline (PT 30 / SL 0.5x / EOD)
- EV/contract $-18.7158, win rate 36.15%, total $-7093.3

## Out-of-sample (2025) check of the chosen policy
- EV/contract $-22.2339, win rate 41.24%, total $-3935.4
