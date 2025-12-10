# ARES ML Advisor Integration Guide

## Overview

The ARES ML Advisor creates a feedback loop between KRONOS (backtesting) and ARES (live trading):

```
    KRONOS Backtests --> Extract Features --> Train Model
            ^                                      |
            |                                      v
    Store Outcome <-- ARES Live Trade <-- Query Model
```

## Quick Start

### 1. Train the Model from KRONOS Data

```bash
# Run the training pipeline
python scripts/train_ares_ml.py --start 2021-01-01 --end 2024-12-01
```

This will:
1. Run a KRONOS backtest on historical data
2. Extract features from each trade
3. Train a Gradient Boosting model
4. Save the model to `quant/.models/`

### 2. Use in ARES

Add this to `trading/ares_iron_condor.py`:

```python
# At the top, add import
try:
    from quant.ares_ml_advisor import get_trading_advice, TradingAdvice
    ML_ADVISOR_AVAILABLE = True
except ImportError:
    ML_ADVISOR_AVAILABLE = False

# In run_daily_cycle(), after getting market data:
def run_daily_cycle(self) -> Dict:
    # ... existing code to check trading window and get market data ...

    market_data = self.get_current_market_data()
    if not market_data:
        return result

    # === NEW: ML ADVISOR CHECK ===
    if ML_ADVISOR_AVAILABLE:
        advice = get_trading_advice(
            vix=market_data['vix'],
            day_of_week=datetime.now(self.tz).weekday(),
            price=market_data['underlying_price']
        )

        logger.info(f"  ML Advice: {advice.advice.value}")
        logger.info(f"  Win Probability: {advice.win_probability:.1%}")
        logger.info(f"  Suggested Risk: {advice.suggested_risk_pct:.1f}%")

        if advice.advice == TradingAdvice.SKIP_TODAY:
            logger.info("ARES: ML advisor suggests skipping today")
            result['actions'].append(f"ML skip: {advice.win_probability:.1%} win prob")
            result['ml_advice'] = {
                'advice': advice.advice.value,
                'win_probability': advice.win_probability,
                'reason': 'Low win probability'
            }
            return result

        # Optionally adjust risk based on ML suggestion
        ml_risk_pct = advice.suggested_risk_pct
        ml_sd_mult = advice.suggested_sd_multiplier
    else:
        ml_risk_pct = self.config.risk_per_trade_pct
        ml_sd_mult = self.config.sd_multiplier
    # === END ML ADVISOR CHECK ===

    # ... continue with trade execution using ml_risk_pct and ml_sd_mult ...
```

### 3. Record Outcomes for Continuous Learning

After a trade closes:

```python
from quant.ares_ml_advisor import (
    get_advisor, MLFeatures, TradeOutcome
)

advisor = get_advisor()

# When position closes
outcome = TradeOutcome.MAX_PROFIT if position.realized_pnl > 0 else TradeOutcome.PUT_BREACHED

features = MLFeatures(
    vix=position.vix_at_entry,
    vix_percentile_30d=50,  # Calculate from history
    vix_change_1d=0,
    day_of_week=datetime.strptime(position.open_date, '%Y-%m-%d').weekday(),
    price=position.underlying_price_at_entry,
    price_change_1d=0,
    expected_move_pct=position.expected_move / position.underlying_price_at_entry * 100,
    win_rate_30d=self.win_count / max(1, self.trade_count),
    avg_pnl_30d=self.total_pnl / max(1, self.trade_count)
)

advisor.record_outcome(
    trade_date=position.open_date,
    features=features,
    outcome=outcome,
    net_pnl=position.realized_pnl
)
```

### 4. Periodic Retraining

As ARES accumulates outcomes, retrain the model:

```python
# Run monthly or after 50+ new trades
advisor = get_advisor()
metrics = advisor.retrain_from_outcomes(min_new_samples=50)

if metrics:
    print(f"Retrained to v{metrics.model_version}")
    print(f"Accuracy: {metrics.accuracy:.1%}")
```

## Feature Descriptions

| Feature | Description | Source |
|---------|-------------|--------|
| `vix` | Current VIX level | Market data |
| `vix_percentile_30d` | VIX position in 30-day range | Calculated |
| `vix_change_1d` | Yesterday's VIX change % | Calculated |
| `day_of_week` | 0=Mon, 4=Fri | System |
| `price_change_1d` | Yesterday's price change % | Market data |
| `expected_move_pct` | 1SD move as % of price | Calculated |
| `win_rate_30d` | Recent 30-day win rate | ARES history |

## Model Details

- **Algorithm**: Gradient Boosting Classifier
- **Calibration**: Isotonic regression for probability calibration
- **Validation**: Walk-forward time series split (no look-ahead bias)
- **Output**: Calibrated probability of MAX_PROFIT outcome

## Honest Limitations

1. **Sample Size**: ~70% win rate means limited loss examples
2. **Regime Changes**: Markets evolve, model may need periodic retraining
3. **Feature Engineering**: Simple features may miss complex patterns
4. **No Guarantees**: Past performance doesn't guarantee future results

## File Locations

- ML Advisor: `quant/ares_ml_advisor.py`
- Training Script: `scripts/train_ares_ml.py`
- Saved Models: `quant/.models/ares_advisor_model.pkl`
- Outcomes Table: `ares_ml_outcomes` (PostgreSQL)
