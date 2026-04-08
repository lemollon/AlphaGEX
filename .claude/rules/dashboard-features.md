# Dashboard Features

## 0DTE Gamma Expiration Tracker (`/gamma/0dte`)
Real-time 0DTE gamma analysis with actionable trading strategies.

**Analysis Views**:
1. **TODAY'S IMPACT** - Directional prediction, gamma impact, Fade the Close (3:45pm), ATM Straddle
2. **WEEKLY EVOLUTION** - Weekly decay patterns, daily risk levels, Theta Farming (Mon-Wed), Delta Buying (Thu-Fri)
3. **VOLATILITY CLIFFS** - Flip points, call/put walls, Pre-Expiration Volatility Scalp (Friday)

**Files**: `frontend/src/app/gamma/0dte/page.tsx`

## WATCHTOWER (ARGUS) - Real-Time 0DTE Gamma Visualization (`/watchtower`)

**Core Features**: Per-strike gamma viz, danger zones, pin strike prediction, magnet identification, gamma regime tracking, ML integration via STARS.

**Market Structure Panel** (9 signals comparing today vs prior day):

| Signal | What It Shows | Trading Use |
|--------|--------------|-------------|
| **Flip Point** | RISING/FALLING/STABLE | Dealer repositioning |
| **±1 Std Bounds** | SHIFTED_UP/DOWN/STABLE/MIXED | Price expectations |
| **Range Width** | WIDENING/NARROWING/STABLE | Vol expansion/contraction |
| **Gamma Walls** | PUT CLOSER/CALL CLOSER/BALANCED | Asymmetric risk |
| **Intraday Vol** | EXPANDING/CONTRACTING/STABLE | Real-time vol vs open |
| **VIX Regime** | LOW/NORMAL/ELEVATED/HIGH/EXTREME | Sizing context |
| **Gamma Regime** | MEAN_REVERSION/MOMENTUM | IC safety vs breakout |
| **GEX Momentum** | STRONG_BULLISH/FADING/etc | Dealer conviction |
| **Wall Break Risk** | HIGH/ELEVATED/MODERATE/LOW | Breakout warning |

**Combined Signal Logic Matrix**:

| Flip Point | Bounds | Width | Gamma Regime | Combined Signal |
|------------|--------|-------|--------------|-----------------|
| RISING | SHIFTED_UP | WIDENING | NEGATIVE | BULLISH_BREAKOUT (HIGH) |
| RISING | SHIFTED_UP | * | POSITIVE | BULLISH_GRIND (MEDIUM) |
| FALLING | SHIFTED_DOWN | WIDENING | NEGATIVE | BEARISH_BREAKOUT (HIGH) |
| FALLING | SHIFTED_DOWN | * | POSITIVE | BEARISH_GRIND (MEDIUM) |
| STABLE | STABLE | NARROWING | POSITIVE | SELL_PREMIUM (HIGH) |
| STABLE | STABLE | NARROWING | NEGATIVE | SELL_PREMIUM_CAUTION (LOW) |
| * | * | WIDENING | STABLE | VOL_EXPANSION_NO_DIRECTION |
| RISING | SHIFTED_DOWN | * | * | DIVERGENCE_BULLISH_DEALERS |
| FALLING | SHIFTED_UP | * | * | DIVERGENCE_BEARISH_DEALERS |

**Wall Break Risk**: HIGH = <0.3% AND (COLLAPSING or NEGATIVE); ELEVATED = <0.3% OR (<0.7% AND COLLAPSING); MODERATE = 0.3-0.7%; LOW = >0.7%. HIGH overrides with `CALL/PUT_WALL_BREAK_IMMINENT`.

**VIX Regime Thresholds**: LOW <15 (directional), NORMAL 15-22 (ICs), ELEVATED 22-28 (widen strikes), HIGH 28-35 (reduce 50%), EXTREME >35 (skip ICs).

**Key Thresholds**: Flip ±$2/±0.3%, Bounds ±$0.50, Width ±5%, Intraday EM ±3%.

**Trade Recommendations** (`/api/watchtower/trade-action`): Exact strikes, sizing, THE WHY, entry/exit rules.

**Signal Tracking** (`/api/watchtower/signals/*`): Log signals, outcome detection at close, performance stats.

**Files**: Backend: `watchtower_routes.py`, Frontend: `watchtower/page.tsx`, Engine: `core/watchtower_engine.py`

## Key Dashboard Components
- `WisdomStatusWidget.tsx` - ML Advisor status
- `DriftStatusCard.tsx` - Backtest vs Live comparison
- `EquityCurveChart.tsx` - Shared equity curve
- `DashboardScanFeed.tsx` - Real-time scan feed
- `ProphetRecommendationWidget.tsx` - PROPHET predictions
- `BotStatusOverview.tsx` - All bots status
