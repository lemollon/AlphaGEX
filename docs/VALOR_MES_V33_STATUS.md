# VALOR MES v33 status: MNQ-to-MES residual catch-up

- **Verdict:** `FAMILY_FAIL_DISCOVERY`
- **Years opened:** 2023 only
- **Years sealed by the firewall:** 2024 and 2025
- **Production/live impact:** none
- **2026:** untouched

All 24 preregistered 2023 cells lost money under the frozen two-tick selection
cost. No cell met the discovery bar, so the code did not load either 2024 or
2025.

The least-negative cell was the 15-minute residual, absolute z-score 2.0,
60-minute hold: 371 trades, -$2,571.75 net, -$6.93 average trade, profit factor
0.72, and $2,820.25 maximum drawdown. The mechanism is rejected rather than
retuned.

Evidence is in `docs/valor_mes_v33/result.json`. The empty CSV ledger is expected:
the preregistration preserves only a selected discovery cell, and no cell was
eligible. Sixty-three focused v33/v8 tests passed before the historical run.
