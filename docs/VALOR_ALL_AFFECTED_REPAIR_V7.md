# VALOR all-affected research repair and recomputation

Protocol: `valor-all-affected-repair-v7-20260923`.

## Scope and operational boundary

The user requested repair and reruns for every strategy affected by the completed-result cache flaw. The active research launcher now uses a single new coordinator, `scripts.valor_research_repair_v7.py`, instead of any v2-v6 run/launch function. Pure evaluators remain pinned and unchanged for direct reconciliation. Old runners are historical code, not approved execution entry points; use the v7 coordinator for further work. This change replaces the active path rather than claiming every archived script has been edited.

No production strategy, MNQ signal, sizing, broker account, order, balance, live-mode setting, SpreadWorks or IronForge source is modified. Historical MNQ studies are included in the audit but its production settings are preserved. One research import in backend/main.py changes; normal deployment restarts the API. The patch is based on main after commit 9fea2d3683f31facb7f9955c125a3dee9e79615a and preserves that independent GEX-expiration correction.

## Why the new runner cannot accept the old completion shortcut

Each result key includes SHA256 hashes of evaluator/coordinator code, strategy parameters, cost scenarios, exact raw-file bytes, relevant GEX source rows, and Python/numeric-library versions. All 18 raw input checksums are recomputed before job reuse. Every result artifact is verified against its own checksum, expected scenario coverage, matching manifest, persisted summary, and trade-ledger accounting where applicable. A parent status of completed is never an early return. Changed identity produces a different run/job; mismatched or corrupted evidence fails closed rather than silently returning old results. Old result tables are read only after evaluation for comparisons, never as a shortcut to new signals.

Source SHA256: c328e3b996cb9543cebbbab0e8bdb2345b88231c4441f33ffd3f709dffa271f8. Source blob: 410bde7bdd06f69e194422035e1ee70fd900795a.

## Exact rerun coverage

63 family/contract/year jobs and 3,276 scenario summaries, not 3,276 independent discoveries:

| Family | Scope | Years | Jobs | Summaries |
|---|---|---|---:|---:|
| v2 pure evaluator recomputation | MES, MNQ, M2K/RTY, MGC, MNG/NG, MCL/CL | 2023-2025 | 18 | 216 |
| v3 exit-specialist recomputation | Same six contracts, both hypotheses each | 2023-2025 | 18 | 72 |
| v4 MES rebuild recomputation | All three MES hypotheses | 2023-2025 | 3 | 18 |
| v5 regenerated GEX filters | MES: all candidate orders regenerated from raw bars before filtering | 2023-2025 | 3 | 216 |
| v6 session recomputation | MES morning/afternoon/close and matched long/short controls | 2023-2025 | 3 | 54 |
| Corrected initial five-rule screen | All six contracts, five horizons, three entry-session choices, two costs | 2023-2025 | 18 | 2700 |

Unlike the prior development gate, no candidate failure skips its 2025 diagnostic evaluation. 2025 and parts of 2026 have been inspected before. All years here are labeled diagnostic/reused data, not untouched holdouts. No automatic strategy promotion occurs.

## Separate reproduction from changed execution

V2, v3, v4 and v6 pure evaluator recomputations deliberately preserve their exact original definitions and compare newly computed P&L/counts to the original saved outputs. Identical outputs would show reproducibility, not failure of the repair. V2's fill-dependent stop/target paths and its conservative unresolved-gap treatment remain explicit inherited limitations; this is not a claim those earlier evaluators are execution-certified.

V5 now builds candidate orders from raw MES bars, applies strictly earlier daily GEX before the daily/position limit, and replays eligible entries. It no longer consumes the previous chosen trade list. However daily gamma sign is constant within a date, so changing the processing order need not change every result. The two SPX/SPY historical series remain distinct reconstructed proxies, not minute GEX or verified dealer inventory. Missing and stale inputs stay unavailable, never implicitly negative. 2025 source coverage may be incomplete and is reported.

The corrected initial screen retains five entry-rule families but changes the invalid same-close and clock-bucket execution: signal uses completed bars, entry uses next minute open, exit uses a scheduled later open at an exact timestamp, and an instrument cannot hold overlapping positions within one strategy. Rolling features reset across unknown minute gaps and contract changes. Exact contract IDs are kept; roll discontinuities cannot become price profits. These are modified execution definitions, so differences versus the original screen are not attributable solely to the result-cache flaw. Entry-session labels do not promise the whole hold stays inside that session.

All result rows carry one-contract costs, gross/net amounts, trade counts, and unresolved/censored coverage. Costs are assumed $3 round-trip fees plus two adverse ticks per side at baseline or four under stress. MNG uses $1,000 per point and $1 per .001 tick. No compounding, portfolio/margin simulation or live certification is implied.

## Raw-data, execution and sample limitations still open

The runner audits all cache bytes and enumerates same-contract in-session minute gaps. It does NOT independently verify those prices with a second vendor or fresh exchange trades/quotes, and does not prove whether any gap is a no-trade minute, outage, halt or selection defect. Unknown positions remain separately unresolved, never zero-P&L or silently forward-filled. Previously censored results therefore remain diagnostic only. Actual broker fees, measured spreads/slippage and publication-time vintages still require separate verification. This repair does not change assumptions until a result becomes profitable.

No new vendor download or paid API request is made. Only two new research tables are written: valor_repair_v7_runs and valor_repair_v7_jobs. Raw caches and old results are preserved. A PostgreSQL advisory lock prevents concurrent research; a separate low-priority process with numerical thread pools capped at one keeps calculations out of the trading event loop. Runtime source mismatch blocks rather than silently mixing evaluators.

## Tests actually run before deployment

32 independent local synthetic tests passed. They cover completed-but-changed code, data/cost/runtime identity changes, corrupt artifacts, altered summaries, incomplete/duplicate coverage, raw byte validation, GEX lag/future-data exclusion, 2025 evaluation despite old gates, causal signal behavior, next-open/exact-time execution, real non-overlap, roll/gap handling, identical cost paths for the corrected initial grid, and a known rising path with profitable momentum and losing reversal. These are unit/regression tests, not real-market profitability evidence or full production integration tests.

Command: `python -m unittest discover -s tests -p test_repair_v7.py -v` in the local repair workspace. In the repository the test file is tests/valor/test_research_repair_v7.py.

## Read-only status

Read valor_repair_v7_runs for current state and manifest; group valor_repair_v7_jobs by family,ticker,year for coverage. The run is complete only when all 63 jobs exist and their artifact/summary checks pass. Prior v2-v6 completed statuses do not satisfy this condition.
