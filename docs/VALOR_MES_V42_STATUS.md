# VALOR MES v42 status

**Recommendation: reject the v41 gap-opposed cluster and do not trade it or
increase size.** It failed its first untouched validation year, so the firewall
kept 2025 unopened and calendar 2026 remains sealed.

## Evidence boundary

- Study: `valor-mes-v42-gap-opposed-validation-20260926`
- Verdict: `FAILED_2024_VALIDATION`
- Code commit: `850ce628bbb003a27f01e66281239a23fb499664`
- Runner SHA-256: `480febb22c46d272290a47264186484556b2f6f6d04d0b8e4752719e8c8d542f`
- 2023 source SHA-256:
  `2b2f14798c8ba726e0ac66fede4e6f028a9324a816d507cf49275315a845a580`
- 2024 source SHA-256:
  `6bc59b8efd4a2256d4d6be2e1114bc57f069219882ec8917ec48f3956f926040`
- Persisted at: `2026-09-26T15:36:11.670682Z`
- Years read: 2023 for causal warmup and 2024 for validation
- Years evaluated: 2024 only; 2025 unopened
- Fill evidence: one-minute trade-print OHLC proxy, not executable bid/ask,
  queue, latency, or market-depth evidence
- Production/broker impact: none; `live_ready=false`, `size_authorized=false`

## Fixed 2024 holdout result

The rule was not retuned: 0.10 prior-ATR opening-range breakout, separate retest
and resumption, gap opposed to trade direction, 1.5R target, and 120-minute hold.

- 43 causal candidate signals; 30 completed trades after full-hold availability
- +$280 at the two-tick selection cost; +$9.33 average; PF 1.392
- $276.75 maximum drawdown; +$82.25 after removing the best month
- +$130 under four-tick stress
- January-June: -$98.50; July-December: +$378.50
- Active-session mean-trade bootstrap 95% interval: -$14.38 to +$34.04

It failed five frozen gates: fewer than 40 trades, PF below 1.40, average below
$12, negative first-half net, and a bootstrap lower bound below zero. Positive
headline net, stress net, and best-month-removed net do not override those
failures.

The largest loss streak was six trades and -$276.75 from January 16 through
February 6. The worst five-active-session window was -$222.50. Per the v42
preregistration, these are descriptive only and cannot become another filter.

## Decision

The apparent 2023 size-up condition did not replicate. Reject it without a
second-generation subgroup search. The next MES study, if any, must introduce a
genuinely independent predictor rather than another filter on the same minute
price path.
