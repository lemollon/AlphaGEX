# MES v6: fixed session hypotheses and directional controls

Study `valor-mes-session-v6-20260923`. This is a new cache-only development study, not a profitable-strategy claim. No vendor requests or broker calls. MNQ, production strategies, balances, sizing, mode settings, SpreadWorks and IronForge source remain unchanged. One research-launcher import changes in backend/main.py and triggers a normal API redeploy; that restart is real operational impact.

## Frozen before results

Each specification trades at most once per Chicago date, one MES contract. No optimization grid and no combination of these separate strategies into a portfolio.

| Hypothesis | Entry time Central | Decision using completed bars | Planned exit Central |
|---|---|---|---|
| Morning continuation | 09:00 | Direction of 08:30-09:00 move; displacement >=25% of opening range; price on matching side of bar-derived VWAP | 12:00 |
| Afternoon continuation | 13:00 | Direction from cash open agrees with immediately preceding 30-minute move and price versus bar-derived VWAP | 14:55 |
| Closing continuation | 14:30 | First 30-minute direction agrees with immediately preceding 30-minute move and price versus bar-derived VWAP | 14:55 |

Initial stop is one first-30-minute range from the completed signal reference, with a four-point floor, rounded to MES ticks. No profit target, trailing stop, SAR, compounding or cost-free breakeven. The purpose is to distinguish session-level continuation from the previously tested frequent short-horizon entries; it does not assert such continuation exists.

For every hypothesis, evaluate the chosen direction, always-long and always-short on the SAME eligible entry dates. Controls have the same risk distance and planned exit, but their opposite stops can create different exit paths. A no-trade control is zero dollars. Only actual signal variants can be selected, not whichever control looks best after the fact.

## Execution and data

Existing checksum-verified MES.v.0 one-minute caches for 2023 and 2024 only initially. Each bar retains exact instrument_id. Completed-bar decisions, following-minute open entries and predetermined future OPEN exits; no use of the exit bar's later high/low. This still idealizes boundary execution and is not a quote-level fill replay. Missing minutes are not filled. Context must be complete up to the decision, but later data quality is never used to erase a signal. Missing entry prices and interrupted positions are unresolved observations, not zero-profit trades. Contract switches do not become P&L jumps. No full-day completeness filter using future information.

Databento specifies ts_event as the beginning of its aggregation interval and omits bars when no trade occurs: https://databento.com/docs/schemas-and-data-formats/ohlcv . MES uses $5 per index point and $1.25 per 0.25-point tick. No use of synthetic ETF execution prices.

Baseline friction: two adverse ticks each side plus assumed $3 round-trip fees = $8 total. Stress: four adverse ticks each side plus those fees = $13 total. This is an assumption, not verified broker billing. Raw paths and decisions are identical between cost scenarios. Gap-through stops fill at the worse observed open, not the stop. Price gaps outside the bracket at entry are charged both sides rather than retrospectively skipping the trade.

Report counts, unresolved fractions, yearly and monthly P&L, direction, profit factor, average trade, worst trade, best-five-trades-removed sensitivity, closed-trade drawdown and resolved-trade minute liquidation-mark drawdown. The latter is not complete intrabar account drawdown; unresolved positions are excluded and no margin/portfolio simulation is claimed.

## Selection

The original numerical standards remain: in EACH of 2023 and 2024, stressed net >0, stress PF >=1.10, at least 100 closed trades and at most 1% unresolved. Separately require the signal to beat BOTH matched-direction controls in each year to advance. Fixed alphabetical tie-break among passers. Only the passing frozen hypothesis and its controls receive a 2025 chronological check. A non-tested 2025 row is explicitly marked not_tested, not zero-return.

2023/24 have repeatedly been examined; this remains selection-biased development. 2025 and portions of 2026 were already examined in prior research and are not blind holdouts. GEX is not used in this study. A passing result would still need genuinely unseen forward validation, verified fees, quotes/latency, and margin/risk assessment.

## Implementation

New tables only: valor_mes_session_v6_state and valor_mes_session_v6_results. A shared PostgreSQL advisory lock prevents concurrent research. Completed studies are not restarted; resumed results must match the source hash. No paid-data package is imported. Evaluation runs in a separate low-priority Python process with numerical thread pools capped at one, rather than in the trading event loop. A missing cache stops the study instead of downloading data.

Source SHA256: d3de6fbd29767a0c89c3816ffbbbcdb17f188952f9cecd75a2f8dea6892aceb0. Source blob: 8f5afb10543abf5adbb7b1940ab62c5035671469. Twenty-nine local synthetic tests passed before deployment. These verify timing, future-data invariance, costs, gaps, rolls, non-overlap, controls and accounting; passing tests is not evidence of profitability.
