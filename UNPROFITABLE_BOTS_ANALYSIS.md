# Why ATHENA, ICARUS, and TITAN Are Not Profitable

## Analysis Date: January 25, 2026

This document analyzes the root causes of unprofitability for the ATHENA, ICARUS, and TITAN trading bots based on a comprehensive code review and data structure analysis.

---

## Executive Summary

After analyzing the codebase, verification reports, and data structures, there are **5 primary root causes** for the unprofitability of these bots:

1. **Strategy Mismatch with Market Conditions** - Bots trading against their optimal market regimes
2. **Disabled Safety Thresholds** - Win probability and VIX filters weakened or disabled
3. **Silent Exit Failures** - Positions not closing when they should
4. **Data Integrity Issues** - NULL realized_pnl values making P&L tracking unreliable
5. **Oracle Calibration Problems** - Predicted win probabilities not matching actual outcomes

---

## Detailed Analysis by Bot

### ATHENA (Directional Spreads on SPY)

**Strategy**: Bull Call Spreads (bullish) and Bear Put Spreads (bearish) based on GEX signals.

**Expected Edge**: Profit when the market moves in the predicted direction.

**Identified Problems**:

| Issue | Severity | Impact |
|-------|----------|--------|
| Direction prediction accuracy | HIGH | Low win rate if GEX direction signals are wrong |
| Exit blocked when pricing fails | CRITICAL | Positions stay open, losses compound |
| Falsy value check skips zero prices | MEDIUM | Incomplete P&L reports |
| Partial close retry missing | HIGH | One leg closed, other stays at risk |

**Code Issues Found** (`trading/athena_v2/trader.py`):
```python
# Line 632-633: Silent exit failure
if current_value is None:
    return False, ""  # SILENT - position stays open!
```

**Expected vs Actual Performance**:
- Strategy requires **accurate direction prediction**
- If Oracle's direction confidence is not well-calibrated, directional bets fail
- NEUTRAL GEX regime (where direction is uncertain) may still be trading

---

### ICARUS (Aggressive Directional Spreads on SPY)

**Strategy**: Same as ATHENA but with AGGRESSIVE parameters:
- 48% min win probability (vs ATHENA's 55%)
- 3% risk per trade (vs 2%)
- 8 max daily trades (vs 5)
- Wider VIX range (12-30 vs 15-25)
- Weaker GEX asymmetry required (1.3/0.77 vs 1.5/0.67)

**Identified Problems**:

| Issue | Severity | Impact |
|-------|----------|--------|
| Lower win probability threshold | HIGH | Takes more marginal trades |
| Larger position sizes | HIGH | Losses amplified |
| More trades per day | MEDIUM | Compounds bad strategy |
| Wider VIX acceptance | HIGH | Trades in unfavorable volatility |
| No retry for failed closes | HIGH | Failed exits abandoned |

**Why ICARUS Loses More Than ATHENA**:
```
ATHENA thresholds:  55% win prob, 2% risk, max 5 trades/day, VIX 15-25
ICARUS thresholds:  48% win prob, 3% risk, max 8 trades/day, VIX 12-30
```

ICARUS trades more often with lower conviction, creating **larger losses more frequently**.

---

### TITAN (Aggressive SPX Iron Condor)

**Strategy**: Iron Condors on SPX with $12 spread widths, multiple trades daily.

**TITAN vs PEGASUS Parameters**:
| Parameter | TITAN (Aggressive) | PEGASUS (Standard) |
|-----------|-------------------|-------------------|
| Risk per trade | 15% | 10% |
| Min win probability | 40% | 50% |
| Strike distance | 0.8 SD | 1.0 SD |
| Profit target | 30% | 50% |
| Cooldown | 30 min | - |

**Identified Problems**:

| Issue | Severity | Impact |
|-------|----------|--------|
| SPX pricing requires production API | CRITICAL | Sandbox fails → positions never close |
| Tighter strikes (0.8 SD) | HIGH | More breaches |
| Lower win probability threshold | HIGH | Takes marginal trades |
| Higher risk per trade (15%) | HIGH | Larger individual losses |
| Partial close limbo | CRITICAL | One leg stays at risk |

**SPX Pricing Issue** (Critical):
SPX options require Tradier's **production API** - the sandbox doesn't support SPX quotes. If the production API key isn't properly configured or has rate limits:
- `get_position_current_value()` returns `None`
- Exit conditions never trigger
- Position stays open until expiration
- Losses compound

---

## Root Cause Analysis

### 1. Strategy Mismatch with Market Conditions

**Problem**: Bots trade in conditions unfavorable to their strategy.

**Evidence from Code** (`quant/oracle_advisor.py`):

```
VIX Regime Impact:
- IRON_CONDOR works best: NORMAL VIX (15-22), POSITIVE GEX
- DIRECTIONAL works best: ELEVATED VIX (22-28), NEGATIVE GEX
```

**What's Happening**:
- ATHENA/ICARUS may take directional trades during POSITIVE GEX (mean-reversion environment)
- TITAN may take Iron Condors during NEGATIVE GEX (trending environment)

### 2. Disabled Safety Thresholds

**From BOT_LOGIC_VERIFICATION_REPORT.md** (January 10, 2026):

> - **Win probability threshold DISABLED** at `signals.py:960-962`
> - **VIX filter DISABLED** at `signals.py:497-498`
> - Signal defaults to 50% confidence if ML and Oracle both fail

**Oracle Changes Made**:
- Monday/Friday penalties REMOVED (these days have historically lower win rates)
- `vix_monday_friday_skip` set to 0 (was 30.0)
- Win probability penalties reduced

These "fixes" allow trading on marginal signals that previously would have been filtered out.

### 3. Silent Exit Failures

**Pattern in ALL bots**:

```python
def _check_exit_conditions(self, pos):
    current_value = self.executor.get_position_current_value(pos)
    if current_value is None:
        return False, ""  # SILENT - position stays open!
    # Profit/loss checks never reached
```

**Impact**:
- Position should close at profit target → pricing fails → stays open
- Market reverses → profit target missed → turns into a loss
- Or: Should close at stop loss → pricing fails → loss compounds

### 4. Data Integrity Issues

**From `diagnose_all_bots.py` Analysis**:

Common database problems:
- `close_time IS NULL` for closed positions
- `realized_pnl IS NULL` for closed positions
- Positions marked 'closed' but P&L never calculated

**Impact**:
- Actual profitability unknown
- Win rates appear artificially low
- Equity curves incomplete

### 5. Oracle Calibration Problems

**Expected Behavior**:
- Oracle predicts 60% win probability → actual wins should be ~60%

**Potential Issue**:
- Oracle predicts 60% → actual wins are only 40%

This means the Oracle is **overconfident** in its predictions, leading bots to take trades that look good on paper but fail in practice.

The analysis script includes this check:
```sql
-- Compare predicted win probability vs actual win rate
SELECT
    win_probability_bucket,
    COUNT(*) as trades,
    actual_win_rate,
    avg_predicted_win_probability
-- If actual_win_rate << avg_predicted, Oracle is miscalibrated
```

---

## Specific Recommendations

### For ATHENA

1. **Raise win probability threshold back to 55%+**
2. **Add direction confirmation** - require multiple signals to agree
3. **Implement pricing fallback** - if MTM fails, use conservative estimates
4. **Avoid NEUTRAL GEX regime** - direction is uncertain

### For ICARUS

1. **Consider disabling entirely** until ATHENA is profitable
2. If keeping active:
   - Raise win probability to 52%+ (not 48%)
   - Reduce risk to 2% (not 3%)
   - Limit to 5 trades/day (not 8)
   - Tighten VIX range to 15-25

### For TITAN

1. **Fix SPX pricing** - ensure production Tradier API is configured
2. **Widen strikes to 1.0 SD** (not 0.8 SD) - more safety margin
3. **Raise win probability threshold to 50%** (not 40%)
4. **Reduce risk per trade to 10%** (not 15%)
5. **Add GEX regime filter** - skip when NEGATIVE GEX

### For Oracle System

1. **Implement calibration monitoring**:
   ```sql
   -- Track predicted vs actual win rates daily
   INSERT INTO oracle_calibration_log (date, predicted_avg, actual_rate)
   ```

2. **Restore Monday/Friday penalties** - historical data shows these days underperform

3. **Re-enable VIX day-specific skips** - high VIX on Fridays is particularly dangerous

4. **Add prediction feedback loop** - retrain when calibration drifts > 10%

---

## Data Queries to Run

To get actual numbers, run the analysis script on production:

```bash
# SSH to Render and run:
python scripts/analyze_unprofitable_bots.py
```

This will show:
- Win/loss counts by bot
- P&L by day of week
- P&L by VIX level
- P&L by GEX regime
- Oracle win probability vs actual outcomes
- Scan activity (why trades are being skipped)

---

## Action Items

| Priority | Action | Bot(s) | Owner |
|----------|--------|--------|-------|
| P0 | Fix SPX pricing for TITAN | TITAN | DevOps |
| P0 | Audit NULL realized_pnl rows and backfill | ALL | Backend |
| P1 | Run analysis script on production | ALL | Quant |
| P1 | Review Oracle calibration data | ALL | ML |
| P1 | Raise win probability thresholds | ICARUS, TITAN | Config |
| P2 | Restore Monday/Friday penalties | ALL (via Oracle) | Quant |
| P2 | Add direction confirmation for ATHENA | ATHENA | Trading |
| P3 | Consider disabling ICARUS until ATHENA profitable | ICARUS | PM |

---

## Conclusion

The bots are unprofitable due to a combination of:

1. **Loosened safety filters** that allow marginal trades
2. **Silent failures** preventing proper exit execution
3. **Data integrity issues** obscuring true performance
4. **Potential Oracle miscalibration** leading to overconfident predictions
5. **Strategy-market mismatch** (trading against optimal conditions)

The most impactful immediate fix is to **run the analysis script on production data** to get actual numbers, then adjust thresholds based on evidence.

---

*Generated by Claude Code analysis - January 25, 2026*
