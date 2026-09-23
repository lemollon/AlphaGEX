# VALOR v8: strict cash-session reruns and a separate management comparison

Study: valor-cash-v8-20260923. Research only. This fixes the identified scheduling, result reuse and incomplete-performance reporting problems; it does not claim all execution uncertainty is solved.

## Scope and operational boundary

Recalculate all six instruments and all 2023-2025 years from verified stored raw minute bars, never from the old result tables. Historical MNQ is audited but no MNQ production logic, configuration, sizing, mode, account or position is changed. No new vendor downloads, broker calls or paid services are created. One research-launch import in backend/main.py changes, so normal Render deployment restarts the API. All existing trading, crypto, SpreadWorks and IronForge source and unrelated concurrent commits are preserved.

## Corrected execution contract

Use published NYSE cash sessions, 08:30-15:00 America/Chicago on full days, 08:30-12:00 on early-close days, excluding holidays and the January 9, 2025 extraordinary closure. Flatten at the scheduled OPEN five minutes before the applicable cash close. Unknown calendar years stop the study. Session membership gates both entries and exits; an RTH entry cannot become an after-hours hold. For commodities this is explicitly a US-equity-cash-hours-only experiment, not their native RTH or a finding about overnight commodity opportunities.

Signals and order levels use completed bars. Market entries use the following observed minute open. Stops and targets are fixed before that price is observed. Entry gaps outside brackets are charged both sides rather than retrospectively skipped. Stop gaps use the worse observed open. Stops win ambiguous stop/target bars; limit targets require a one-tick trade-through, which remains an execution scenario rather than proof of queue priority. Trailing updates take effect on the next bar. Scheduled open exits never inspect that exit bar's later high/low. Positions truly cannot overlap within a strategy.

Every candidate is accounted for as skipped, closed or unresolved. An unknown interval or contract change retains the unresolved position and blocks further entries on that date. The study does not invent prices, silently realize zero P&L, or call resolved-trade totals a complete account return. When any position is unresolved, net_dollars and profit_factor are null; separately labeled resolved diagnostics remain available. Subsequent dates restart flat only for diagnostic testing, not as an executable recovery claim.

Raw OHLCV and contract IDs pass timestamp, duplicate, finite-value, geometry and tick-grid checks. Byte hashes are recomputed, but this is not independent vendor verification. Databento omits minutes with no trades; unknown causes require trades/quotes or status data, not automatic filling.

## Strategy coverage

All years are evaluated even when earlier promotion gates failed. There are 18 historical ticker-year jobs and 1,476 related scenario summaries: 162 per MES year, 66 per year for each of MNQ, M2K/RTY, MGC, MNG/NG and MCL/CL. MNG starts late 2023; partial data is not called three full years.

The initial five-rule screen, v2 price rules, v3 exit specialists, v4 MES setups, v5 daily-GEX filters, and v6 session hypotheses are regenerated from raw bars. Original pure feature definitions are source-pinned; old run/evaluate functions and old completion flags are not used. V4 previous-day context follows the previous actual, complete cash session, including early closes. Current-day future completeness is not an entry gate. V5 filters candidate orders before the position/day limit; its SPX and SPY inputs remain separate lagged daily proxies, not intraday dealer inventory or verified publication vintages.

A common corrected execution model changes several old assumptions, including v2 fill-dependent brackets and limit-touch handling. This is a controlled specification rerun, not a single-factor claim that all P&L differences were caused by trading hours. The separate recorded-signal comparison below is the hours-only contrast.

## Recorded-signal management comparison

The existing preserved MESZ6 archive (SHA256 6905cc403754594824f313421ab644ae787c55d40f42fcd071465d5ece858ef9) covers September 15 00:00 UTC to September 22 12:42 UTC, 2026. The repository's allowlisted production-method replay is used with identical recorded signals and identical current default management/config in both arms: all-session versus strict cash-only/pre-close flat. Compare two hypothetical minute paths and two slippage assumptions, eight scenarios total. SAR is not independently tuned in this paired experiment.

This does NOT recover historical configurations, ML feedback, portfolio sizing, exact event-time GEX or broker quotes. It starts flat with one MES; scan-to-MESZ6 mapping is a period assumption. The two OHLC paths are scenarios, not proven bounds. All-session maintenance/EOD behavior inherits the replay's explicit unverified carry-to-next-open assumption. Consequently this is a conditional management experiment, not exact production parity, a three-year GEX backtest, or independent holdout. If archive coverage or current method compatibility fails, this track is visibly blocked while historical price studies can proceed. Such a run is labeled completed_with_recorded_track_blocked, not fully completed.

## Costs, evidence and validity

Baseline is two adverse ticks per side plus an assumed $3 round-trip fee; stress uses four ticks per side plus the same fee. MES costs are $8 and $13. Raw price paths in the common historical kernel are identical across cost assumptions. Actual fees, bid/ask, latency, impact and protective-order execution remain unverified. No compounding or portfolio/margin simulation and no live promotion occur. 2023-2025 and parts of 2026 have already been examined; all are labeled reused diagnostic data, not untouched OOS.

Result identity includes evaluator and production-source hashes, parameters, costs, raw bytes, GEX snapshot, calendar and numeric-library versions. Checks precede any result reuse, even for a completed parent. Evidence checksum, expected scenario count, unique identity, ledger/count/month/cost reconciliation and cash-window invariants are checked before accepting results. New tables only: valor_cash_v8_runs and valor_cash_v8_jobs. Shared advisory lock, low-priority subprocess and one numerical thread prevent concurrent research and keep work out of the trading event loop.

## Verification before running

56 local regression tests passed before deployment. Tests cover holidays, early closes, DST, causal entries/exits, strict flattening, unknown exposure, tick geometry, gaps, stop/limit precedence, trailing updates, non-overlap, fees, GEX timing, and stale/corrupt result rejection. The worker also runs real-module synthetic integration checks over all six instruments before historical evaluation. Their runtime status is reported in Render logs. Unit/integration checks are not evidence of profitability.

Core blob: 3a1f0bfa063123480355424311e820679a3637a0. Coordinator blob: 11aa1676652757c93fb65d5c2d7ee8524784e0df. Test blob: dfbf47f06fb3c078e70b20ef1e69bd5f7dc8e770.

Primary calendar sources are embedded in scripts/valor_cash_engine_v8.py: ICE/NYSE 2023-2025 and 2024-2026 holiday releases, plus the Carter national-day-of-mourning closure announcement. Databento bar convention: https://databento.com/docs/schemas-and-data-formats/ohlcv .
