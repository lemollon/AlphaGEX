# MES v5: paired historical GEX filters

Study: `valor-mes-gex-overlay-v5-20260923`.

This is an exploratory matched-trade filter study, not a new live strategy or a full three-year intraday-GEX backtest. MNQ and production trading rules, account balances, sizing, and live-mode settings are unchanged. The research launcher change restarts the AlphaGEX API through its normal deployment; it is not zero operational impact. No SpreadWorks or IronForge source is edited. The worker reads an existing shared historical table but never imports or runs either project's code.

## Fixed comparison

Use only the saved 2023/2024 v4 MES entry and exit ledgers, pinned to source SHA256 `a89b8b6eb6b0cf51896672f9238c09e2e8030bbc72ea0f366bd50d8b2dc7ea3c`. Do not retune stops, targets, or entry rules and do not replace trades blocked by a GEX filter. This isolates the arithmetic contribution of filtering the original cohort; it does not reproduce a fully regenerated strategy that can use later entries.

For each of the three prior hypotheses, compare all GEX-matched trades, positive-GEX-only trades, and negative-GEX-only trades. Unmatched trades are excluded from the matched baseline as well as filtered variants. Retained plus rejected matched P&L must equal the matched baseline. Missing and zero GEX are never guessed to be negative.

## Sources and timing limitations

1. `gex_structure_daily`, symbol SPX, net_gamma: ORATS-derived end-of-day gamma/OI proxy, built by `scripts/populate_gex_structures.py` with a default 0-7 DTE universe and assumed call-minus-put exposure. This is not measured dealer inventory. Its stored price labels and interpolated strike sign-crossings are not used as MES prices or genuine aggregate gamma-flip targets.
2. `sw_gamma_daily`, net_gex: the seeded SPY baseline series. It is a separate reconstructed proxy, not an interchangeable copy of SPX GEX. The full historical reconstruction and as-published vintages are not verified.

Queries on September 23, 2026 found both series have 250 observations in 2023 and 252 in 2024. They disagree in sign on 83/250 dates in 2023 and 49/252 in 2024. Those differences are a reason to keep the series separate, not proof either is wrong. Dense TradingVolatility intraday SPY observations start in late 2025; sparse older GEX snapshots do not establish a 2023/2024 minute archive.

Use source dates strictly before the Chicago decision date. Primary lag: previous observed source session, maximum age four calendar days. Timing sensitivity: two prior source sessions, maximum age seven calendar days. No same-day EOD input, backward filling, or overnight synthetic GEX is allowed. A date lag alone does not establish original vendor release time or revision-free historical availability. Source-date rows are hashed and preserved with evidence. Daily proxy results cannot validate real-time GEX operation.

## Costs, gates, and outputs

The v4 paths retain two adverse ticks per side plus an assumed $3 fee for baseline ($8/MES round trip), and four per side plus that fee for stress ($13). Friction scenarios use identical raw paths. Closed-trade drawdown is not total account/intratrade drawdown. Missing-data/contract-switch positions remain separately reported as censored.

Each development year must show stressed profit >0, stressed profit factor >=1.10, >=100 closed trades and <=1% censored for the numerical gate. Also report whether the two-session timing sensitivity is positive in both years. A numerical pass is not promotion: source-vintage validation, independently unseen testing, real execution costs, and portfolio risk checks remain outstanding. Repeated use of development data entails selection bias. Neither 2025 nor all of 2026 is an untouched holdout; this worker reads neither year's outcomes.

There are 144 summaries: 2 years x 3 fixed setups x 2 sources x 2 lags x 3 filters x 2 cost scenarios. These are not 144 independent strategy discoveries.

Only new `valor_mes_gex_v5_state` and `valor_mes_gex_v5_results` are written. The worker uses the shared advisory lock, skips a completed study, refuses mixed code/input hashes, and makes no vendor downloads or broker calls. Source blob: `430e1c4aa5e9e7f0a6a25381749fdeea6156e9e1`; source SHA256: `29631d32438470918e6155f1c8a965646792ced0fb06373025527af9efe032af`.

Twenty-two local synthetic tests passed before deployment. They verify strict date lags, same-day/future exclusion, missing/stale handling, timestamp validity, base-ledger and paired-cohort accounting, unchanged entries under cost scenarios, duplicate-year and future-year selection rejection, and the separation between numerical gates and live approval. Unit tests are not profitability evidence.
