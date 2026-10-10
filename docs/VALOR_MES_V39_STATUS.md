# VALOR MES v39 status

**Recommendation: reject the overnight-extreme sweep-rejection family and do
not use its apparent subgroups to avoid trades or increase size.** The frozen
2023 discovery run failed every cell after costs and produced too few signals.
Per the preregistered firewall, 2024 and 2025 were not opened; calendar 2026
remains sealed.

## Evidence boundary

- Study: `valor-mes-v39-overnight-sweep-20260926-r1`
- Result schema: `valor-mes-v39-result/1.0.1`
- Code commit: `6881b96efa04a3efb24ff7472e30ebb62abfcdd8`
- Source checksum: `8e36bd24ed7a5a36e9817e58cc669542760bc6a7306fe4a49d83cdbcefd82f13`
- Persisted at: `2026-09-26T14:46:55.407381Z`
- Data opened: cached, checksummed Databento MES `ohlcv-1m`, calendar 2023 only
- Sessions: 154 usable; 96 excluded because causal prior ATR was unavailable
- Signal evaluation: completed five-minute bars throughout the cash session;
  entry at next one-minute open; stop-first ambiguous bars; target requires a
  one-tick trade-through
- Cost selection view: $3 round-trip fee plus two adverse ticks on entry and
  two adverse ticks on exit; four ticks each side is the stress case
- Limitation: one-minute trade-print OHLC proxy, not executable bid/ask, queue,
  latency, or market-depth evidence
- Production and broker state: unchanged; `live_ready=false`

The first persisted result used the same frozen strategy but selected a
three-trade diagnostic cell for cluster reporting. Revision `r1` corrected only
the diagnostic selector to require at least 40 observations when available.
No signal, fill, cost, pass/fail, or validation rule changed.

## Frozen discovery matrix

All dollar figures are per one MES contract. `Net 2t` and `Avg 2t` include the
$3 fee and two adverse ticks per side. `Net 4t` is the four-tick-per-side stress
case.

| Sweep depth (ATR) | Target | Hold | Trades | Net 2t | Avg 2t | PF 2t | MDD 2t | Best month removed | Net 4t | Pass |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 0.10 | 1.5R | 30m | 47 | -$359.75 | -$7.65 | 0.669 | $495.75 | -$457.00 | -$594.75 | No |
| 0.10 | 1.5R | 60m | 46 | -$700.50 | -$15.23 | 0.547 | $700.50 | -$806.50 | -$930.50 | No |
| 0.10 | 1.5R | 120m | 37 | -$779.75 | -$21.07 | 0.478 | $787.25 | -$968.25 | -$964.75 | No |
| 0.10 | 2.0R | 30m | 47 | -$418.50 | -$8.90 | 0.615 | $493.75 | -$460.75 | -$653.50 | No |
| 0.10 | 2.0R | 60m | 46 | -$704.25 | -$15.31 | 0.544 | $704.25 | -$840.25 | -$934.25 | No |
| 0.10 | 2.0R | 120m | 37 | -$627.25 | -$16.95 | 0.580 | $741.25 | -$870.75 | -$812.25 | No |
| 0.20 | 1.5R | 30m | 5 | -$40.00 | -$8.00 | 0.699 | $76.00 | -$128.25 | -$65.00 | No |
| 0.20 | 1.5R | 60m | 5 | -$92.50 | -$18.50 | 0.625 | $158.50 | -$200.75 | -$117.50 | No |
| 0.20 | 1.5R | 120m | 3 | -$45.25 | -$15.08 | 0.708 | $88.00 | -$154.75 | -$60.25 | No |
| 0.20 | 2.0R | 30m | 5 | -$40.00 | -$8.00 | 0.699 | $76.00 | -$128.25 | -$65.00 | No |
| 0.20 | 2.0R | 60m | 5 | -$148.75 | -$29.75 | 0.397 | $158.50 | -$200.75 | -$173.75 | No |
| 0.20 | 2.0R | 120m | 3 | -$71.50 | -$23.83 | 0.538 | $88.00 | -$154.75 | -$86.50 | No |

The least-bad adequately populated diagnostic cell was 0.10 ATR / 1.5R / 30
minutes: 47 trades, 44.7% win rate, -$359.75 at the selection cost, -$7.65 per
trade, PF 0.669, and -$594.75 under four-tick stress. It missed both the
150-trade discovery minimum and every profitability/robustness gate.

## Win/loss cluster review

No condition qualified as a frozen avoidance rule and no condition qualified
for size-up. Descriptive results below must not be converted into a rule:

- Strongest loss pattern: prior 15-minute return opposed to the trade, 12
  trades, -$32.58 average, PF 0.162, -$391.00 net, bootstrap upper bound
  -$10.39. It looks bad, but 12 is below the required 40 trades.
- Larger-sample loss warnings: low directional efficiency had 45 trades, PF
  0.647, -$368.75 net, but bootstrap upper bound was +$5.23; first sweeps had 43
  trades, PF 0.765, -$217.75 net, but bootstrap upper bound was +$8.67. Neither
  passed the preregistered avoidance test.
- Strongest apparent favorable pattern: flat prior 15-minute return, 9 trades,
  +$15.75 average, PF 3.17, +$96.75 even at four-tick stress, but bootstrap
  lower bound was -$6.89 and the sample missed the 40-trade minimum.
- A prior 30-minute return aligned with the trade had 15 trades, +$6.42
  average, PF 1.56, and +$21.25 at four-tick stress, but also missed the
  required average, sample, and positive-bootstrap gates.
- Largest loss streak: five trades from 2023-07-17 through 2023-07-28,
  -$151.25. Largest win streak: four trades from 2023-05-04 through 2023-05-31,
  +$108.00.
- Worst five-active-session window: -$235.50 ending 2023-11-22. Best
  five-active-session window: +$128.75 ending 2023-05-03. These are sparse
  signal windows, not five consecutive calendar sessions.
- Winners averaged 4.19 points MAE and 11.19 points MFE. Losers averaged 8.36
  points MAE and 4.50 points MFE. These are diagnostics, not entry filters.

## Decision

Verdict: `FAMILY_FAIL_DISCOVERY`.

Do not trade or optimize this family further. The next MES study should change
the mechanism, not tweak sweep depth, target, hold, or cluster filters. Keep
2024, 2025, and 2026 sealed for that next preregistered mechanism.
