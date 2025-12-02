# SPX WHEEL TRADING SYSTEM - COMPLETE WORKFLOW

## The Billionaire Trader's Framework

This document explains EXACTLY how the backtest drives live trading. No gaps. No vague parts.

---

## THE CORE LOOP

```
┌──────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   STEP 1: CALIBRATE                                                      │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │  ./scripts/calibrate_spx_wheel.sh                                │   │
│   │                                                                  │   │
│   │  What happens:                                                   │   │
│   │  1. Tests 12 parameter combinations (4 deltas × 3 DTEs)          │   │
│   │  2. Runs EACH on Polygon historical option data                  │   │
│   │  3. Calculates: win rate, return, drawdown, Sharpe ratio         │   │
│   │  4. Picks the BEST based on your optimization goal               │   │
│   │  5. Saves parameters to database                                 │   │
│   │                                                                  │   │
│   │  Output you see:                                                 │   │
│   │  Delta=0.15 DTE=30: Win=78.2%, Return=+12.3%, DD=8.1%, Sharpe=1.5│   │
│   │  Delta=0.15 DTE=45: Win=81.4%, Return=+14.1%, DD=6.2%, Sharpe=2.3│   │
│   │  Delta=0.20 DTE=45: Win=76.9%, Return=+18.2%, DD=9.4%, Sharpe=1.9│   │
│   │  ... etc for all 12 combinations ...                             │   │
│   │                                                                  │   │
│   │  BEST: Delta=0.15, DTE=45 (highest Sharpe)                       │   │
│   └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│   STEP 2: TRADE DAILY                                                    │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │  ./scripts/run_spx_daily.sh                                      │   │
│   │                                                                  │   │
│   │  What happens:                                                   │   │
│   │  1. Loads the calibrated parameters (Delta=0.15, DTE=45)         │   │
│   │  2. Checks VIX - skip if outside 12-35 range                     │   │
│   │  3. Gets current SPX price                                       │   │
│   │  4. Calculates strike: SPX - (SPX × (4% + delta×15%))            │   │
│   │     Example: SPX=5800 → Strike = 5800 - 522 = 5280 (rounded)     │   │
│   │  5. Finds Friday closest to DTE target                           │   │
│   │  6. Gets option price (Polygon or estimate)                      │   │
│   │  7. Opens position, logs to database                             │   │
│   │                                                                  │   │
│   │  Output you see:                                                 │   │
│   │  OPENED: O:SPX241220P05280000 @ $15.40                           │   │
│   │          Strike: $5280, Exp: 2024-12-20, Contracts: 2            │   │
│   └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│   STEP 3: MONITOR                                                        │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │  ./scripts/check_spx_performance.sh                              │   │
│   │                                                                  │   │
│   │  What you see:                                                   │   │
│   │                                                                  │   │
│   │  LIVE RESULTS:                                                   │   │
│   │    Trades: 24                                                    │   │
│   │    Winners: 19                                                   │   │
│   │    Losers: 5                                                     │   │
│   │    Win Rate: 79.2%                                               │   │
│   │    Total P&L: +$47,230                                           │   │
│   │                                                                  │   │
│   │  BACKTEST COMPARISON:                                            │   │
│   │    Live Win Rate: 79.2%                                          │   │
│   │    Backtest Win Rate: 81.4%                                      │   │
│   │    Divergence: -2.2% ✓ WITHIN TOLERANCE                          │   │
│   │                                                                  │   │
│   │  If divergence > 10%: RECALIBRATE                                │   │
│   └──────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│   STEP 4: RECALIBRATE (monthly or on divergence)                         │
│   └── Go back to STEP 1                                                  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## WHAT DATA IS USED

### Backtest Data (Calibration Phase)
- **Source**: Polygon.io historical option prices
- **Ticker Format**: `O:SPX{YYMMDD}P{strike*1000:08d}`
- **Example**: `O:SPX231220P05800000` = SPX Put, Dec 20 2023, Strike $5800
- **Verification**: Every trade logged with exact ticker - you can check on Polygon

### Live Trading Data
- **SPX Price**: Polygon real-time (symbols: SPX, ^SPX, I:SPX)
- **VIX**: For market condition filtering
- **Option Prices**: Polygon or broker feed

### Data Quality Tracking
Every backtest shows:
```
DATA QUALITY:
  Real Data:    145 (89.2%)
  Estimated:    17 (10.8%)
```

If estimated is high, the backtest is less reliable.

---

## THE EXACT PARAMETERS

### What We Test During Calibration

| Parameter | Values Tested | What It Means |
|-----------|---------------|---------------|
| Delta | 0.15, 0.20, 0.25, 0.30 | Higher = closer to ATM = more premium but more risk |
| DTE | 30, 45, 60 | Higher = more time value but slower capital turnover |

### What Gets Saved

After calibration, these are stored in the database:

```python
WheelParameters:
    put_delta: 0.15           # From optimization
    dte_target: 45            # From optimization
    max_margin_pct: 0.50      # Use 50% of capital
    contracts_per_trade: 1
    max_open_positions: 3
    min_vix: 12               # Don't trade below
    max_vix: 35               # Don't trade above

    # BACKTEST RESULTS (for comparison)
    backtest_win_rate: 81.4%
    backtest_total_return: +14.1%
    backtest_max_drawdown: 6.2%
    calibration_date: 2024-12-02
```

---

## STRIKE CALCULATION (EXACT FORMULA)

```python
# Target OTM put
strike_offset = spot_price × (0.04 + put_delta × 0.15)

# For 0.20 delta and SPX at 5800:
strike_offset = 5800 × (0.04 + 0.20 × 0.15)
             = 5800 × 0.07
             = 406

target_strike = 5800 - 406 = 5394
rounded_strike = 5395  # Round to nearest $5
```

---

## POSITION MANAGEMENT

### When Position Expires

**OTM (SPX > Strike)**: Keep full premium
```
Premium received: $1,540 (per contract)
Settlement: $0
P&L: +$1,540 ✓ WIN
```

**ITM (SPX < Strike)**: Cash settlement loss
```
Strike: $5280
Settlement: $5200
Loss: ($5280 - $5200) × 100 = $8,000

Premium received: $1,540
Settlement loss: -$8,000
Net P&L: -$6,460 ✗ LOSS
```

---

## DIVERGENCE HANDLING

| Divergence | Action |
|------------|--------|
| < 5% | Normal variance, continue |
| 5-10% | Monitor closely |
| > 10% | RECALIBRATE immediately |
| > 20% | Stop trading, investigate |

---

## COMPLETE FILE REFERENCE

| File | Purpose |
|------|---------|
| `scripts/calibrate_spx_wheel.sh` | Find optimal parameters |
| `scripts/run_spx_daily.sh` | Execute daily trades |
| `scripts/check_spx_performance.sh` | Monitor vs backtest |
| `trading/spx_wheel_system.py` | Core optimizer + trader logic |
| `backtest/spx_premium_backtest.py` | Historical backtester |

---

## SCHEDULE

| Day | Action |
|-----|--------|
| **Daily** (Mon-Fri) | Run `run_spx_daily.sh` |
| **Weekly** | Run `check_spx_performance.sh` |
| **Monthly** | Run `calibrate_spx_wheel.sh` |
| **On 10%+ Divergence** | Run `calibrate_spx_wheel.sh` |

---

## START HERE

```bash
# 1. First time setup - calibrate
./scripts/calibrate_spx_wheel.sh 2022-01-01

# 2. Review the parameters chosen
# (shown in calibration output)

# 3. Start trading daily
./scripts/run_spx_daily.sh

# 4. Check performance weekly
./scripts/check_spx_performance.sh
```

---

## THE BILLIONAIRE MINDSET

1. **Every parameter is data-driven** - Not guesses, not "typical" values, but TESTED on YOUR chosen historical period

2. **Complete audit trail** - Every trade logged with exact option ticker, verifiable on Polygon

3. **Continuous feedback loop** - Live performance compared to backtest, recalibrate when they diverge

4. **No black boxes** - You see every combination tested, every trade made, every P&L calculation

5. **Adapts to market** - Monthly recalibration ensures parameters stay optimal for current conditions

---

This is NOT "set and forget". This is a SYSTEM that:
- Learns from history (backtest)
- Applies that learning (calibrated parameters)
- Monitors itself (performance comparison)
- Adapts (recalibration)

You always know EXACTLY what it's doing and WHY.
