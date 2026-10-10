# VALOR MES v35 status: dual-leader breadth breakout

- **Verdict:** `FAILED_2023_DISCOVERY`
- **Years opened:** 2023 only
- **Years sealed:** 2024 and 2025
- **Production/live impact:** none
- **2026:** untouched

The frozen MNQ+M2K breadth rule produced 425 MES trades. Raw P&L was
$1,433.75, but the two-tick case was -$1,966.25, or -$4.63 per trade, with
profit factor 0.86 and $2,827.25 maximum drawdown. Four-tick stress was
-$4,091.25.

The independent breadth confirmation did not improve the MES transfer; it
reduced the gross move per trade. The rule is rejected without tuning. Evidence
and the reviewable ledger are in `docs/valor_mes_v35/`.
