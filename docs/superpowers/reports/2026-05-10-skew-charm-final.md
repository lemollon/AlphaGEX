# Skew + Charm (Phase 2) Backtest Report

**Period:** 2023-01-03 to 2025-12-05
**Total trades:** 420
**Overall WR:** 19.5%
**Overall mean PnL/trade:** $-9.36
**Total PnL:** $-3930
**BULL:** n=420, WR=19.5%
**BEAR:** n=0, WR=0.0%
**Time-stop %:** 1.2%

## Bin Summary (by composite z bucket)

| Action | Z-bucket | n | WR | Mean | Median | Std | Sharpe | RealPct |
|---|---|---|---|---|---|---|---|---|
| BULL | 1.5-3.0 | 1 | 0.0% | $-10.20 | $-10.20 | $0.00 | 0.00 | -5.4% |
| BULL | 3.0-6.0 | 2 | 0.0% | $-15.70 | $-15.70 | $7.00 | -2.24 | -17.1% |
| BULL | >6.0 | 417 | 19.7% | $-9.32 | $-7.70 | $10.25 | -0.91 | -3.9% |


## GO/NO-GO

```
In-sample: n=277, WR=21.7%, RR=0.27, EV=$-9.00/trade, time-stop=0.4%
OOS: n=143, WR=15.4%
VERDICT: NO-GO
  fail: WR<66%
  fail: RR<1.5
  fail: EV<+$5
```
