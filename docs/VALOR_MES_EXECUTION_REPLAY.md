# MES execution replay and rollover repair

This patch is for paper validation. It does not certify live trading readiness.

## Corrected contract handling

MES, MNQ and RTY entries adopt the next quarterly contract at Sunday 17:00
Chicago time before CME's customary Monday roll date. The legacy MES accessor
uses the same calculation. CME lists September 14, 2026 as the roll date:
https://www.cmegroup.com/trading/equity-index/rolldates.html

Quotes resolve the requested broker instrument to its exact streamer symbol.
Cache keys include expiry. Monitoring, paper closes, EOD closes and equity
snapshots use each position's stored contract. Continuous Yahoo data is no
longer accepted as an executable contract quote. Broker bid/ask timestamps
remain the freshness source; receipt time cannot refresh an old snapshot.

An expired or unpriced legacy position remains unresolved, rather than being
silently renamed or closed using the new contract's price. Broker settlements
and historical paper contract attribution still need reconciliation. Monthly
commodity roll policies are outside this equity-index repair.

## Offline replay

`scripts/replay_valor_execution.py` uses only Python's standard library. It
never imports the live trading service, connects to a broker, or opens a DB.
It extracts explicitly named production stop, trailing, session and SAR method
bodies using AST. Method decorators are removed; fills and persistence are
in-memory adapters. Source hashes are included in the report.

Inputs are `MESZ6_1m.csv.gz` and `mes_scan_inputs.jsonl.gz` from the existing
research export. The supported calendar window is September 15 00:00 UTC to
September 22 12:42 UTC, 2026, end exclusive. Missing open-market minutes,
duplicate candles, off-grid prices and naive timestamps stop the replay.

```bash
python -u scripts/replay_valor_execution.py \
  --data-dir /tmp/mes_research_c18cootu \
  --round-trip-fee 3 --fee-source assumed
```

The fee is per MES contract round trip, excluding slippage. Replace it with
verified account commissions and exchange/regulatory fees when available.
Outputs use a new timestamped subdirectory; source files are never overwritten.
Use `--config sanitized_config.json` for a saved configuration; otherwise the
report explicitly uses current code defaults, not historical configuration.

The default twelve scenarios compare SAR off/on, OHLC/OLHC assumed paths,
and one/two/four ticks of adverse slippage per fill. The default observation
cadence is 15 seconds; `--cadence 1` is a sensitivity experiment, not tick data.
Normal entries occur at the next minute's open after the recorded scan.
Only observed simulated prices update MFE and trailing stops. Gap fills use
the current simulated price, never a missed stop's ideal trigger price.
One contract, single-position/cooldown, per-MES daily negative-P&L limit and
loss-streak pauses are modeled. Results separate RTH and overnight entries.

## What overnight and SAR mean here

Production defines overnight as 15:00–08:00 Chicago time. Under the current
no-loss trailing defaults, the overnight emergency stop is eight points
versus fifteen RTH. The 1.25-point stop/two-point target belong to the alternate
fixed-stop mode and are not layered into trailing mode. The five-point max
loss rule and SAR often trigger before the emergency stop.

The production SAR method closes a position but its immediate reversal fails
the shared minimum 60-second cooldown. Replay counts SAR closes, suppressed
reversals and actual reversal entries separately. This patch does not bypass
the cooldown or invent a delayed-reversal queue.

## Remaining limits and release gates

- Recorded signals lack historical n+1 GEX inputs and exact contract identity.
  This is conditional execution replay, not full signal regeneration or an
  independent holdout. Historical config and ML feedback are not recovered.
- Minute candles do not reveal event order, executable bid/ask, latency or
  scheduler phase. The two paths are scenarios, not provable best/worst bounds.
- Position sizing, cross-instrument portfolio losses/margin and prior open
  positions are excluded. Trades start from a flat one-MES research account.
- The EOD scheduler requests closes at 16:00 CT, when maintenance starts.
  No executable closing quote is established by these bars. The replay carries
  remaining positions to reopening and labels EOD execution unverified.
- Final open positions are reported separately. Drawdown samples the simulated
  path and includes marked open P&L; it is not a bound on actual intratrade loss.
- Verified account costs, exact-contract paper quotes, legacy-position
  reconciliation, broker protective-order/recovery checks, and forward paper
  validation remain necessary before considering live deployment.

Do not restart/deploy the Render service before preserving the raw research
files and replay reports: this experiment currently lives in instance-local
`/tmp`. Run the branch script in a separate temporary checkout without changing
the running application's files. This pull request must remain unmerged until
that data is preserved and the production quote changes are checked in paper.
