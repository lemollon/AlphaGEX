# AlphaGEX Trading Workflow

## Complete End-to-End Trading Process

This document describes the complete trading workflow from market open to trade execution and exit.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ALPHAGEX TRADING WORKFLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐   │
│   │  DATA   │───▶│ ANALYZE │───▶│ DECIDE  │───▶│ EXECUTE │───▶│ MONITOR │   │
│   │ COLLECT │    │ REGIME  │    │ STRATEGY│    │  TRADE  │    │  EXIT   │   │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘   │
│       │              │              │              │              │          │
│       ▼              ▼              ▼              ▼              ▼          │
│   GEX, VIX       Classify      Select         Place         Track P&L       │
│   Prices         Conditions    Strategy       Orders        Close at        │
│   Greeks         Score         Size Pos       Record        Target/Stop     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Data Collection (Every 60 Seconds)

### What Happens
The system continuously fetches market data from multiple sources to build a complete picture of current conditions.

### Data Sources

| Source | Data Retrieved | Update Frequency | Used For |
|--------|---------------|------------------|----------|
| Trading Volatility API | Net GEX, Call Wall, Put Wall, Flip Point | 60 seconds | Regime classification |
| Polygon API | VIX level, Option prices, Historical data | 60 seconds | IV Rank, Greeks |
| Tradier API | Real-time quotes, Account balance | 5 seconds | Execution, Risk |

### Code Flow

```python
# Location: data/unified_data_provider.py

def collect_market_data(symbol: str) -> MarketData:
    """
    Collects all required market data for trading decisions.

    Called: Every 60 seconds by scheduler
    Returns: MarketData object with all indicators
    """

    # 1. Fetch GEX data from Trading Volatility
    gex_data = trading_vol_api.get_gex(symbol)
    # Returns: {net_gex, spot_price, call_wall, put_wall, flip_point}

    # 2. Fetch VIX from Polygon
    vix = polygon_api.get_vix()
    # Returns: Current VIX level (e.g., 18.5)

    # 3. Calculate IV Rank
    iv_rank = calculate_iv_rank(vix, historical_vix_252d)
    # Formula: (Current - 52wk Low) / (52wk High - 52wk Low) * 100

    # 4. Get current price
    spot_price = polygon_api.get_quote(symbol)

    # 5. Calculate momentum indicators
    momentum = calculate_momentum(symbol)
    # Returns: {rsi, macd, trend_ma20, trend_ma50}

    return MarketData(
        symbol=symbol,
        spot_price=spot_price,
        gex=gex_data,
        vix=vix,
        iv_rank=iv_rank,
        momentum=momentum,
        timestamp=datetime.now()
    )
```

### Validation Checks

Before proceeding, data is validated:

```python
def validate_market_data(data: MarketData) -> tuple[bool, str]:
    """
    Ensures data quality before trading decisions.
    """

    # Check 1: Spot price is reasonable
    if data.spot_price <= 0:
        return False, "Invalid spot price"

    # Check 2: GEX data exists
    if data.gex.net_gex is None:
        return False, "Missing GEX data"

    # Check 3: VIX is in valid range
    if not (5 <= data.vix <= 80):
        return False, f"VIX {data.vix} outside valid range"

    # Check 4: Data is fresh (< 5 minutes old)
    age = datetime.now() - data.timestamp
    if age.total_seconds() > 300:
        return False, f"Data is stale ({age.total_seconds()}s old)"

    return True, "Data valid"
```

---

## Phase 2: Regime Classification

### What Happens
The Market Regime Classifier analyzes collected data to determine current market conditions and recommend an action.

### Regime Types

| Regime | GEX | VIX | Trend | Characteristics |
|--------|-----|-----|-------|-----------------|
| **POSITIVE_GAMMA** | > 0 | Any | Any | Dealers hedge by selling rallies, buying dips. Mean reversion. |
| **NEGATIVE_GAMMA** | < 0 | > 20 | Any | Dealers amplify moves. Momentum environment. |
| **NEUTRAL** | ~0 | 12-18 | Range | Low volatility, choppy. No clear edge. |

### Classification Logic

```python
# Location: core/market_regime_classifier.py

def classify_regime(data: MarketData) -> RegimeClassification:
    """
    Determines market regime from market data.

    Returns: RegimeClassification with action, confidence, and parameters
    """

    # Step 1: Determine GEX regime
    if data.gex.net_gex > 500_000_000:  # +$500M
        gex_regime = "POSITIVE"
        gex_score = 70
    elif data.gex.net_gex < -500_000_000:  # -$500M
        gex_regime = "NEGATIVE"
        gex_score = 70
    else:
        gex_regime = "NEUTRAL"
        gex_score = 30

    # Step 2: Determine trend
    if data.spot_price > data.momentum.ma20 > data.momentum.ma50:
        trend = "UPTREND"
        trend_score = 20
    elif data.spot_price < data.momentum.ma20 < data.momentum.ma50:
        trend = "DOWNTREND"
        trend_score = 20
    else:
        trend = "RANGE"
        trend_score = 10

    # Step 3: VIX assessment
    if data.vix > 30:
        vix_signal = "HIGH_VOL"
        vix_adjustment = -15  # Reduce confidence
    elif data.vix < 15:
        vix_signal = "LOW_VOL"
        vix_adjustment = -10  # Less premium available
    else:
        vix_signal = "NORMAL"
        vix_adjustment = 0

    # Step 4: Calculate confidence
    confidence = min(100, gex_score + trend_score + vix_adjustment)

    # Step 5: Determine recommended action
    action = determine_action(gex_regime, data.iv_rank, trend, data.vix)

    return RegimeClassification(
        regime=gex_regime,
        trend=trend,
        vix_signal=vix_signal,
        confidence=confidence,
        recommended_action=action
    )
```

### Action Determination Matrix

```python
def determine_action(gex_regime, iv_rank, trend, vix) -> str:
    """
    Decision matrix for recommended trading action.
    """

    # Rule 1: High IV + Positive GEX = SELL_PREMIUM
    if iv_rank >= 50 and gex_regime == "POSITIVE":
        return "SELL_PREMIUM"

    # Rule 2: Negative GEX + Below Flip = BUY_CALLS
    if gex_regime == "NEGATIVE" and vix > 20:
        if spot_price < gex_flip_point:
            return "BUY_CALLS"
        else:
            return "BUY_PUTS"

    # Rule 3: Low IV + Strong Trend = Buy Direction
    if iv_rank < 30 and trend != "RANGE":
        if trend == "UPTREND":
            return "BUY_CALLS"
        else:
            return "BUY_PUTS"

    # Rule 4: Uncertain conditions = Stay Flat
    return "STAY_FLAT"
```

---

## Phase 3: Strategy Selection

### What Happens
Based on the regime classification and recommended action, a specific options strategy is selected.

### Strategy Mapping

| Action | Trend | Strategy Selected | Description |
|--------|-------|-------------------|-------------|
| SELL_PREMIUM | UPTREND | Bull Put Spread | Sell OTM put spread, collect premium |
| SELL_PREMIUM | DOWNTREND | Bear Call Spread | Sell OTM call spread, collect premium |
| SELL_PREMIUM | RANGE | Iron Condor | Sell both put and call spreads |
| BUY_CALLS | Any | Long Call | Buy ATM or OTM call |
| BUY_PUTS | Any | Long Put | Buy ATM or OTM put |
| STAY_FLAT | Any | No Trade | Wait for better conditions |

### Strategy Configuration

```python
# Location: trading/config/strategies.py

STRATEGY_CONFIGS = {
    "BULL_PUT_SPREAD": {
        "short_delta": 0.30,      # Sell 30-delta put
        "long_delta": 0.15,       # Buy 15-delta put (protection)
        "dte_target": 45,         # 45 days to expiration
        "profit_target": 50,      # Close at 50% profit
        "stop_loss": 200,         # Close if option doubles
        "roll_at_dte": 7,         # Roll at 7 DTE
        "min_credit": 0.50,       # Minimum credit required
        "max_width": 5,           # Maximum strike width
    },

    "IRON_CONDOR": {
        "call_short_delta": 0.16,
        "call_long_delta": 0.10,
        "put_short_delta": 0.16,
        "put_long_delta": 0.10,
        "dte_target": 45,
        "profit_target": 50,
        "stop_loss": 200,
        "roll_at_dte": 7,
        "min_credit": 1.00,
    },

    "LONG_CALL": {
        "delta": 0.50,            # ATM call
        "dte_target": 30,
        "profit_target": 100,     # Double money
        "stop_loss": 50,          # Cut losses at 50%
    }
}
```

---

## Phase 4: Position Sizing (Kelly Criterion)

### What Happens
Before executing, the system calculates optimal position size using Kelly Criterion based on historical performance.

### Kelly Formula

```
Kelly % = (Win Rate × Avg Win - Loss Rate × Avg Loss) / Avg Loss

Example:
- Strategy: Bull Put Spread
- Win Rate: 68%
- Avg Win: 15% of premium
- Avg Loss: 25% of premium

Kelly = (0.68 × 15 - 0.32 × 25) / 25
     = (10.2 - 8.0) / 25
     = 8.8%

With Half-Kelly (safety): 4.4% of capital
```

### Position Sizing Logic

```python
# Location: trading/mixins/position_sizer.py

def calculate_position_size(
    strategy: str,
    account_balance: float,
    confidence: int,
    vix: float
) -> PositionSize:
    """
    Calculates optimal position size using Kelly Criterion.
    """

    # Step 1: Get strategy statistics
    stats = get_strategy_stats(strategy)
    # stats = {win_rate: 0.68, avg_win: 0.15, avg_loss: 0.25}

    # Step 2: Calculate full Kelly
    win_rate = stats.win_rate
    loss_rate = 1 - win_rate
    avg_win = stats.avg_win_pct / 100
    avg_loss = stats.avg_loss_pct / 100

    kelly = (win_rate * avg_win - loss_rate * avg_loss) / avg_loss

    # Step 3: Check for negative expectancy
    if kelly <= 0:
        return PositionSize(
            size_pct=0,
            contracts=0,
            reason="Negative expectancy - do not trade"
        )

    # Step 4: Apply Half-Kelly for safety
    half_kelly = kelly * 0.5

    # Step 5: Apply confidence adjustment
    adjusted_kelly = half_kelly * (confidence / 100)

    # Step 6: Apply VIX stress reduction
    if vix > 30:
        adjusted_kelly *= 0.70  # -30% for high VIX
    elif vix > 20:
        adjusted_kelly *= 0.85  # -15% for elevated VIX

    # Step 7: Apply hard cap (never risk more than 15%)
    final_pct = min(adjusted_kelly, 0.15)

    # Step 8: Calculate dollar amount and contracts
    position_dollars = account_balance * final_pct
    contract_value = 100  # Options multiplier
    max_loss_per_contract = calculate_max_loss(strategy)
    contracts = int(position_dollars / max_loss_per_contract)

    return PositionSize(
        size_pct=final_pct * 100,
        contracts=max(1, contracts),
        dollars=position_dollars,
        kelly_raw=kelly * 100,
        kelly_adjusted=final_pct * 100
    )
```

---

## Phase 5: Trade Execution

### What Happens
The system validates the trade, places the order (paper or live), and records the position.

### Pre-Execution Checks

```python
# Location: trading/mixins/trade_executor.py

def validate_trade(trade: TradeSignal, account: Account) -> tuple[bool, str]:
    """
    Validates trade before execution.
    """

    # Check 1: Sufficient buying power
    required_margin = calculate_margin(trade)
    if account.buying_power < required_margin:
        return False, f"Insufficient margin (need ${required_margin:,.0f})"

    # Check 2: Not exceeding max positions
    open_positions = get_open_positions()
    if len(open_positions) >= MAX_POSITIONS:
        return False, f"At max positions ({MAX_POSITIONS})"

    # Check 3: Market is open
    if not is_market_open():
        return False, "Market is closed"

    # Check 4: No conflicting positions
    for pos in open_positions:
        if pos.symbol == trade.symbol and pos.strategy == trade.strategy:
            return False, "Already have position in this strategy"

    # Check 5: Circuit breaker not triggered
    if is_circuit_breaker_active():
        return False, "Circuit breaker active - trading halted"

    return True, "Trade validated"
```

### Order Execution

```python
def execute_trade(trade: TradeSignal, mode: TradingMode) -> TradeResult:
    """
    Executes trade in paper or live mode.
    """

    # Step 1: Get current option prices
    option_chain = get_option_chain(trade.symbol, trade.expiration)
    legs = build_order_legs(trade, option_chain)

    # Step 2: Validate liquidity
    for leg in legs:
        spread = leg.ask - leg.bid
        spread_pct = spread / leg.mid * 100
        if spread_pct > 10:  # >10% spread
            return TradeResult(
                success=False,
                reason=f"Wide spread on {leg.symbol}: {spread_pct:.1f}%"
            )

    # Step 3: Execute order
    if mode == TradingMode.PAPER:
        # Paper mode: Record to database only
        order_id = f"PAPER-{uuid.uuid4().hex[:8]}"
        fill_price = calculate_mid_price(legs)

    elif mode == TradingMode.LIVE:
        # Live mode: Place actual order via Tradier
        order_response = tradier.place_order(
            legs=legs,
            order_type="credit" if trade.is_credit else "debit",
            price=trade.limit_price
        )
        order_id = order_response.order_id
        fill_price = order_response.fill_price

    # Step 4: Record position in database
    position_id = record_position(
        symbol=trade.symbol,
        strategy=trade.strategy,
        legs=legs,
        entry_price=fill_price,
        contracts=trade.contracts,
        order_id=order_id
    )

    # Step 5: Log decision for transparency
    log_decision(
        decision_type="ENTRY",
        action=trade.action,
        what=f"OPEN {trade.strategy} on {trade.symbol}",
        why=trade.reasoning,
        how=f"Placed {len(legs)}-leg order at ${fill_price:.2f}"
    )

    return TradeResult(
        success=True,
        position_id=position_id,
        order_id=order_id,
        fill_price=fill_price
    )
```

---

## Phase 6: Position Monitoring

### What Happens
Open positions are continuously monitored for exit conditions.

### Monitoring Loop

```python
# Location: trading/position_monitor.py

def monitor_positions():
    """
    Runs every 60 seconds to check exit conditions.
    """

    positions = get_open_positions()

    for position in positions:
        # Get current price
        current_price = get_position_value(position)

        # Calculate P&L
        pnl_pct = calculate_pnl_percentage(position, current_price)

        # Check exit conditions
        exit_reason = check_exit_conditions(position, pnl_pct)

        if exit_reason:
            execute_exit(position, exit_reason, current_price)
```

### Exit Conditions

```python
def check_exit_conditions(position: Position, pnl_pct: float) -> Optional[str]:
    """
    Checks all exit conditions for a position.
    """

    config = STRATEGY_CONFIGS[position.strategy]

    # Condition 1: Profit target reached
    if pnl_pct >= config["profit_target"]:
        return f"PROFIT_TARGET ({pnl_pct:.1f}% >= {config['profit_target']}%)"

    # Condition 2: Stop loss hit
    if pnl_pct <= -config["stop_loss"]:
        return f"STOP_LOSS ({pnl_pct:.1f}% <= -{config['stop_loss']}%)"

    # Condition 3: Time-based exit (DTE threshold)
    dte = (position.expiration - date.today()).days
    if dte <= config.get("roll_at_dte", 7):
        return f"TIME_EXIT (DTE={dte} <= {config['roll_at_dte']})"

    # Condition 4: Expiration day
    if position.expiration == date.today():
        return "EXPIRATION"

    # No exit condition met
    return None
```

### Exit Execution

```python
def execute_exit(position: Position, reason: str, exit_price: float):
    """
    Executes position exit.
    """

    # Step 1: Calculate final P&L
    pnl = calculate_realized_pnl(position, exit_price)

    # Step 2: Close position (place closing order)
    if trading_mode == TradingMode.LIVE:
        close_order = build_closing_order(position)
        tradier.place_order(close_order)

    # Step 3: Update database
    update_position_closed(
        position_id=position.id,
        exit_price=exit_price,
        exit_reason=reason,
        realized_pnl=pnl
    )

    # Step 4: Record to closed trades
    record_closed_trade(position, exit_price, reason, pnl)

    # Step 5: Update strategy statistics
    update_strategy_stats(position.strategy, pnl)

    # Step 6: Log decision
    log_decision(
        decision_type="EXIT",
        action="CLOSE",
        what=f"CLOSE {position.strategy} on {position.symbol}",
        why=reason,
        how=f"Closed at ${exit_price:.2f}, P&L: ${pnl:+,.2f}"
    )

    # Step 7: Send alert
    if pnl < -100:
        send_alert(f"Position closed with loss: ${pnl:,.2f}", level="HIGH")
```

---

## Phase 7: Feedback Loop

### What Happens
After each closed trade, strategy statistics are updated and fed back into position sizing.

### Statistics Update

```python
# Location: trading/mixins/performance_tracker.py

def update_strategy_stats(strategy: str, pnl: float):
    """
    Updates strategy statistics after trade closes.
    """

    # Step 1: Get all closed trades for this strategy (last 90 days)
    closed_trades = get_closed_trades(
        strategy=strategy,
        since=datetime.now() - timedelta(days=90)
    )

    # Step 2: Calculate statistics
    total = len(closed_trades)
    winners = [t for t in closed_trades if t.pnl > 0]
    losers = [t for t in closed_trades if t.pnl <= 0]

    win_rate = len(winners) / total if total > 0 else 0
    avg_win = mean([t.pnl_pct for t in winners]) if winners else 0
    avg_loss = abs(mean([t.pnl_pct for t in losers])) if losers else 0

    # Step 3: Calculate expectancy
    if avg_loss > 0:
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    else:
        expectancy = 0

    # Step 4: Only update if we have enough trades
    if total >= 5:
        update_database_stats(
            strategy=strategy,
            win_rate=win_rate * 100,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            expectancy=expectancy,
            total_trades=total
        )

        logger.info(f"Updated {strategy} stats: {total} trades, "
                   f"{win_rate*100:.1f}% win rate, {expectancy:.2f}% expectancy")

    # Step 5: Check for negative expectancy (block strategy)
    if expectancy < 0 and total >= 10:
        disable_strategy(strategy)
        send_alert(
            f"Strategy {strategy} blocked: negative expectancy ({expectancy:.2f}%)",
            level="CRITICAL"
        )
```

---

## Complete Workflow Timing

| Phase | Frequency | Duration | Trigger |
|-------|-----------|----------|---------|
| Data Collection | Every 60s | ~2s | Scheduler |
| Regime Classification | On data update | ~100ms | After data |
| Strategy Selection | On regime change | ~50ms | After regime |
| Position Sizing | Before trade | ~100ms | Trade signal |
| Trade Execution | On signal | ~1-5s | Validated signal |
| Position Monitoring | Every 60s | ~500ms | Scheduler |
| Stats Update | On trade close | ~200ms | Position closed |

---

## Trading Bots

AlphaGEX runs three specialized trading bots:

### ATLAS (SPX Wheel)
- **Focus:** Cash-secured puts on SPX
- **Strategy:** Sell premium, collect theta
- **Parameters:** Calibrated via backtest optimization
- **Location:** `trading/spx_wheel_system.py`

### PROMETHEUS (Premium Seller)
- **Focus:** Credit spreads on SPY
- **Strategy:** Iron condors, bull put/bear call spreads
- **Parameters:** GEX-driven regime detection
- **Location:** `core/autonomous_paper_trader.py`

### SOLOMON (Directional)
- **Focus:** Directional spreads during negative gamma
- **Strategy:** Long calls/puts during momentum regimes
- **Parameters:** Momentum and breakout detection
- **Location:** `trading/solomon_directional_spreads.py`

---

## Troubleshooting

### No Trades Being Placed
1. Check regime classification: `/api/gex/SPY/regime`
2. Verify recommended_action is not "STAY_FLAT"
3. Check position count vs MAX_POSITIONS
4. Verify market is open

### Wrong Strategy Selected
1. Review decision matrix in `core/market_regime_classifier.py`
2. Check input data (GEX, VIX, trend) values
3. Verify IV rank calculation

### Position Not Closing
1. Check position_monitor.py is running
2. Verify exit conditions in strategy config
3. Check if position is in database with status="OPEN"

### Statistics Not Updating
1. Verify trade was recorded in autonomous_closed_trades
2. Check if minimum trade count (5) reached
3. Review logs for update_strategy_stats errors
