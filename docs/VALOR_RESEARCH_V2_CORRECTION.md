# VALOR research correction and v2 protocol - 2026-09-23

## Status of earlier claims

The earlier three-year tables are preserved, but must be treated as provisional screening, not verified account-level profitability or live readiness. The implemented first grid was futures-price-only: it did not join historical GEX. Its use of clock buckets did not guarantee non-overlapping positions, its entries used the same bar close that formed the signal, and its continuous-contract returns were not protected from contract switches. The subsequent expanded search also had a startup indentation error and NaN-to-integer warmup failure. These are implementation problems, not evidence that a market is impossible to trade profitably.

MNG's research contract multiplier was wrong by a factor of ten. CME specifies 1,000 MMBtu and a .001 minimum move worth $1. Research v2 uses $1,000 per price point, not $100. Production contract math and historical paper ledgers require separate reviewed reconciliation; this research patch does not rewrite them.

Sources:
- https://www.cmegroup.com/articles/faqs/micro-henry-hub-natural-gas-futures-and-options-frequently-asked-questions.html
- https://databento.com/docs/schemas-and-data-formats/ohlcv
- https://databento.com/docs/examples/symbology/continuous

Databento OHLCV timestamps denote bar starts, absent no-trade minutes are not printed, and its continuous contracts are original unadjusted contract prices. These conventions matter for lookahead, indicator windows, and rollover treatment.

## What v2 tests

Three frozen candidate families per ticker, rather than one mandatory shared signal:

| Ticker | Candidate families |
|---|---|
| MES | Range re-entry, low-volatility reversal, opening-range rejection |
| MNQ | Trend-confirmed breakout, opening-range breakout, trend pullback |
| RTY/M2K | Range re-entry, opening-range rejection, volatility-expansion breakout |
| MGC | Trend pullback, trend-confirmed breakout, range re-entry |
| NG/MNG | Volatility-expansion breakout, trend-confirmed breakout, opening-range breakout |
| CL/MCL | Opening-range breakout, trend pullback, volatility-expansion breakout |

This initial corrected pass uses each instrument's configured daytime research window, two maximum holding times (60 and 120 minutes), a 4-ATR stop and 2R target, and two friction scenarios. These are hypotheses, not optimized or proven strategies. The GEX overlay and overnight-specialized follow-up remain separate work.

## Execution and limitations

- Signals use completed one-minute bars. Entry occurs at the next contiguous bar open, not the signal's own close.
- Actual position exit controls the next eligible entry; clock buckets are not position limits.
- Baseline friction is two adverse ticks per side, stress is four ticks per side, both plus an assumed $3 round-trip commission/fee. Friction combines spread and slippage assumptions; it is not historical bid/ask evidence or verified broker pricing.
- Both stop and target touched in a minute: stop-first scenario. A stop gap uses the observed opening price, not an ideal missed trigger.
- Indicator windows reset on missing minutes and contract changes. No filled-forward synthetic minutes and no cross-contract synthetic P&L.
- Missing data/rolls while a position is open leave that position censored, rather than fabricating a close. Subsequent contiguous segments restart flat. Censored counts must accompany any P&L: the conditional result is not a complete executable account backtest.
- Stored drawdown is closed-trade drawdown, not full intrabar account drawdown or a margin study.
- Raw data, checksums, trade ledgers, censoring records, monthly results, and source hashes are preserved for review.
- MNG data starts in November 2023 and is sparse. Eighteen ticker-year jobs does not mean eighteen complete calendar years.
- Nothing in this module submits broker orders or changes production strategy rules, positions or account balances.

## Validation discipline

Select using 2023-2024, then evaluate the selected specification chronologically on 2025. Because 2025 was already examined in the initial grid, it cannot honestly be described as a blind holdout. Portions of 2026 were also used in earlier discovery. This runner does not download 2026; an actually untouched future/held-out period must be identified after the strategy is frozen. Passing code tests is not evidence of profitability.

## Cost and concurrency controls

Render's run table showed three completed original runs at 2026-09-23 11:24:26 UTC. Their stored provider estimates sum to $61.20. That is a sum of estimates, not a verified invoice or verified remaining credit balance; the earlier $20.40 figure was per run.

V2 acquires a PostgreSQL advisory lock for the lifetime of a dedicated connection. Every ticker-year is cached once in Postgres before evaluating candidates. A paid request is reserved in the ledger before issuance. An interrupted request without a saved cache is not automatically retried. Completed jobs are not rerun on startup.

Each new download is quoted first. New estimated reservations, including 10% headroom, are capped at $25. Prior run estimates with 25% headroom plus new reservations must remain within the existing $125 research ceiling. This is a research cost guard, NOT proof of free-credit availability. Actual account billing still needs confirmation.

The former public GET /run-year is disabled with HTTP 410, so arbitrary web requests cannot start paid downloads. Status and cost endpoints do not download market data. No API keys are exposed.

## Checks performed

The exact source blob b813e30fac210f5327849ba2f68942aa811e7aa3 passed 13 local synthetic tests: multiplier/tick value, warmup, next-bar entries, non-overlap, future-data perturbation invariance, contract switches, missing entry bars, in-position gaps, ambiguous stop/target ordering, adverse gap fills, transaction costs, malformed data, and serialization/research labeling. Three additional local route checks verified disabled paid GET, fixed date bounds, and read-only status. These are unit checks, not a full production integration test.

New tables: valor_research_v2_state, valor_research_v2_results, valor_research_bar_cache, valor_research_download_ledger. Study ID: valor-contract-v2-20260923.
