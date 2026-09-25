# VALOR MES v34 status: MNQ breakout transferred to MES

- **Verdict:** `FAILED_2023_DISCOVERY`
- **Years opened:** 2023 only
- **Years sealed:** 2024 and 2025
- **Production/live impact:** none
- **2026:** untouched

The one preregistered rule generated 497 MES trades. Raw price P&L was
$3,206.25, but the two-tick selection case was -$769.75, or -$1.55 per trade,
with profit factor 0.95 and $2,008.25 maximum drawdown. Four-tick stress was
-$3,254.75.

The MNQ breakout therefore transfers some gross direction to MES, but not enough
movement per trade to clear MES costs. No filter or exit was changed after the
result; 2024 and 2025 were not loaded. Evidence and the reviewable 497-trade
ledger are in `docs/valor_mes_v34/`.
