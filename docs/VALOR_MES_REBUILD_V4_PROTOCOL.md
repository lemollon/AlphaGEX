# MES-only rebuild v4: predeclared cache study

User scope: keep MNQ unchanged; prioritize a fresh MES strategy. This patch changes no trading rule, sizing, live-mode setting, position, account, or MNQ code. It adds a research script and tests, and replaces the completed v3 startup launcher with the MES-only launcher. Normal Render deployment restarts the API; it is not a no-restart change. SpreadWorks, IronForge, and crypto source are not edited.

## Why this is a new research pass

The initial MNQ +$7,627 screen was not validated: overlapping clock buckets, same-close entries and roll handling compromise it. Preserve MNQ as requested, but do not label it live-ready. Corrected v2/v3 studies tested different specifications, so their losses do not establish the precise corrected result for that original MNQ candidate. Neither those studies nor this MES pass joins historical GEX. 2025 and part of 2026 have already been examined; neither entire year is a blind holdout.

## Frozen hypotheses

1. Opening acceptance/retest: two completed five-minute closes beyond the first 30-minute range, followed by a later retest and directional rejection aligned with bar-based VWAP. Structure stop and 3R target; 180-minute cap.
2. Prior-extreme reclaim: sweep beyond the previous complete cash-session high/low and close back inside. Target prior-range midpoint, stop beyond the sweep; 120-minute cap. Prior and current contracts must match.
3. Gap-fill after opening failure: moderate overnight gap of 0.2-0.8 prior 20-session cash ATR, failure of opening range away from the gap, target previous close; 90-minute cap.

All candidates: 08:30-15:00 America/Chicago cash-session context, no new entries after 13:00, one attempt per candidate per session, completed five-minute inputs and next contiguous minute-open entry. Reward >=1.5 planned risk and >=5 times the baseline cost allowance. Risk must clear twice the cost allowance and be <=3 five-minute ATR. Fixed rules, not a parameter sweep. Each strategy has its own hypothetical one-contract account; candidate results must not be summed as a portfolio.

## Execution and costs

MES $5 per index point, .25 tick. Baseline two adverse ticks per side + assumed $3 round trip; stress four ticks per side + same fee. Same raw trade paths across friction scenarios. Orders are determined before the next open, not filtered using the future opening price. An opening gap outside the bracket is flattened and charged; later stop gaps use observed open. Stop-first when high/low touches both bracket sides. Fills are OHLC scenarios, not quote-level evidence. Stops are not guaranteed live fills. Missing minutes, contract changes and incomplete tape censor unresolved positions; these are reported separately, not profitable closes. Drawdown is closed-trade only. VWAP is a minute typical-price/volume approximation.

## Selection

Reuse 2023/24 as development. Require positive stress net, stress PF >=1.10, >=100 closed trades, and <=1% censored positions in EACH year. Select highest minimum yearly stress-net/closed-drawdown ratio; deterministic ties. Only a passer receives the already-seen 2025 chronological check. No passer => 2025 NOT TESTED, not zero. These are research gates, not claims of statistical significance or live readiness. Repeated research on the same years risks overfitting; future unseen data remains essential.

## Storage, cost, safety

Study: `valor-mes-rebuild-v4-20260923`. Uses existing MES 2023-25 Postgres Parquet caches with pinned SHA256 values. No vendor calls or new download cost; no broker imports. Writes only `valor_mes_v4_state` and `valor_mes_v4_results`; full trade/censor ledgers gzip-preserved. Shared advisory lock serializes research; completed studies do not rerun; source changes cannot mix results. An absent/mismatched cache stops work. No destructive operations.

The exact source blob `eff90a32e66323fc3b356afe0e3279d61615c00b` and matching test suite passed 26 local synthetic cases before deployment. Tests cover next-bar fills, adverse gaps, stop-first, non-overlap, one-attempt limits, missing minutes, roll censoring, complete bars/opening ranges, input validation, costs, signal-prefix invariance and selection excluding 2025. This is not production integration or profitability validation.
