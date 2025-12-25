# Oracle Override Logic - Technical Architecture

## Overview

Oracle is the central AI advisory system that aggregates multiple signals (GEX, ML predictions, VIX regime, market conditions) and provides curated recommendations to each trading bot (ARES, ATHENA, ATLAS). The override logic allows the system to adjust or completely override ML model predictions based on additional market context.

## Architecture Flow

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                      ORACLE                              │
                    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │
                    │  │ GEX Signals │  │ ML Model    │  │ VIX Regime  │      │
                    │  │  (Kronos)   │  │(5 ensemble) │  │   Check     │      │
                    │  └─────────────┘  └─────────────┘  └─────────────┘      │
                    │                         │                                │
                    │              ┌──────────┴──────────┐                    │
                    │              │  Claude Validation  │                    │
                    │              │   (ADJUST/OVERRIDE) │                    │
                    │              └──────────┬──────────┘                    │
                    └─────────────────────────┼───────────────────────────────┘
                                              │
                     ┌────────────────────────┼────────────────────────┐
                     │                        │                        │
                     ▼                        ▼                        ▼
                ┌─────────┐              ┌─────────┐              ┌─────────┐
                │  ARES   │              │  ATLAS  │              │ ATHENA  │
                │   IC    │              │  Wheel  │              │ Spreads │
                └─────────┘              └─────────┘              └─────────┘
```

## Override Mechanisms

### 1. Claude AI Validation (Primary Override)

When enabled, Claude AI reviews every ML prediction and can issue one of three recommendations:

| Recommendation | Description | Effect |
|----------------|-------------|--------|
| **AGREE** | ML prediction is sound | No changes to prediction |
| **ADJUST** | Small confidence change needed | Applies confidence adjustment (-0.10 to +0.10) |
| **OVERRIDE** | Significant change required | Applies adjustment + logs override reason |

#### Confidence Adjustment Logic

```python
if claude_analysis.recommendation in ["ADJUST", "OVERRIDE"]:
    # Adjust win probability within safe bounds
    win_probability = max(0.40, min(0.85,
        win_probability + claude_analysis.confidence_adjustment
    ))
```

The adjustment is clamped between -10% and +10% to prevent extreme swings.

### 2. Suggested Risk Percentage (`suggested_risk_pct`)

Oracle provides a recommended position size based on win probability using a modified Kelly Criterion:

| Win Probability | Risk Per Trade | Rationale |
|-----------------|----------------|-----------|
| >= 75% | 10% | High confidence - full Kelly |
| 70-75% | 8% | Strong signal |
| 65-70% | 6% | Moderate confidence |
| 60-65% | 5% | Conservative |
| < 60% | 0% (STAY_OUT) | Below threshold |

**Bot Implementation:**

- **ARES**: Uses `suggested_risk_pct` directly for Iron Condor sizing
- **ATHENA**: Uses `suggested_risk_pct * 0.5` (halved for directional risk)
- **ATLAS**: Uses `suggested_risk_pct` for cash-secured put sizing

### 3. SD Multiplier Override (`suggested_sd_multiplier`)

Controls how wide strikes should be placed:

| Win Probability | SD Multiplier | Strike Width |
|-----------------|---------------|--------------|
| >= 75% | 0.9 | Tighter (more premium) |
| 65-75% | 1.0 | Standard |
| < 65% | 1.2 | Wider (safer) |

**Effect on ARES Iron Condor:**
- SD 0.9: Short strikes at ~0.9 standard deviations from spot
- SD 1.0: Standard 1 SD placement
- SD 1.2: Conservative 1.2 SD placement (less premium, higher probability)

### 4. GEX Wall Strike Overrides

When `use_gex_walls=True`, Oracle provides specific strikes based on gamma exposure walls:

```python
class OraclePrediction:
    use_gex_walls: bool = False
    suggested_put_strike: Optional[float] = None  # Based on Put Wall
    suggested_call_strike: Optional[float] = None  # Based on Call Wall
```

**GEX Wall Logic:**
- **Put Wall**: Price level with maximum put gamma - acts as support
- **Call Wall**: Price level with maximum call gamma - acts as resistance
- Strikes are placed just beyond these walls to maximize probability of expiring worthless

## Decision Flow by Bot

### ARES (Iron Condor) Override Flow

```
1. Calculate base ML win probability
2. Apply VIX regime adjustment:
   - VIX > 32: STAY_OUT (hard skip)
   - VIX > 25: Reduce confidence 10%
   - VIX < 15: Reduce confidence 5%
3. Apply GEX regime adjustment:
   - POSITIVE regime: +5% confidence
   - NEGATIVE regime: -5% confidence
4. Claude Validation (if enabled):
   - AGREE: Proceed with ML prediction
   - ADJUST: Apply confidence adjustment
   - OVERRIDE: Apply adjustment + use override_advice
5. Final Decision:
   - win_prob >= 65%: ENTER_NOW
   - win_prob >= 55%: ENTER_CONSERVATIVE
   - win_prob < 55%: STAY_OUT
```

### ATHENA (Directional Spreads) Override Flow

```
1. Get GEX data from Kronos
2. Check ML signal from gex_signal_integration
3. Query Oracle for direction confirmation
4. Apply Claude Validation:
   - Check for OVERRIDE on direction
   - Apply confidence adjustment
5. Calculate R:R using GEX walls
6. Final Decision based on:
   - Direction alignment
   - R:R ratio >= 2:1
   - Win probability >= 55%
```

### ATLAS (Wheel Strategy) Override Flow

```
1. Calculate base win probability
2. Check VIX regime:
   - VIX > 30: Skip (too volatile)
   - VIX 20-30: Reduce risk 50%
3. Apply Circuit Breaker check
4. Claude Validation for entry timing
5. Final Decision:
   - ENTER: Sell cash-secured put
   - WAIT: Hold for better entry
   - STAY_OUT: Skip entirely
```

## Override Priority Order

When multiple override signals conflict, they are applied in this priority:

1. **Circuit Breaker** (highest) - Hard stop, overrides everything
2. **VIX Hard Skip** - If VIX > threshold, skip regardless of other signals
3. **Claude OVERRIDE** - If Claude says override, apply its advice
4. **GEX Wall Adjustments** - Strike placement recommendations
5. **ML Prediction** (lowest) - Base prediction before adjustments

## Claude Analysis Data Structure

```python
@dataclass
class ClaudeAnalysis:
    analysis: str                    # Detailed analysis text
    confidence_adjustment: float     # -0.10 to +0.10
    risk_factors: List[str]          # What could go wrong
    opportunities: List[str]         # What looks favorable
    recommendation: str              # "AGREE", "ADJUST", "OVERRIDE"
    override_advice: Optional[str]   # What to do instead (if OVERRIDE)

    # Transparency fields
    raw_prompt: str                  # Full prompt sent to Claude
    raw_response: str                # Raw Claude response
    tokens_used: int                 # Total tokens consumed
    response_time_ms: int            # Response latency
    model_used: str                  # e.g., "claude-3-5-sonnet-20241022"

    # Anti-hallucination fields
    hallucination_risk: str          # "LOW", "MEDIUM", "HIGH"
    data_citations: List[str]        # Data points Claude cited
```

## Anti-Hallucination Measures

Oracle enforces strict anti-hallucination rules in Claude prompts:

1. **Citation Requirement**: Every claim must reference a specific data point
2. **Data Bounds**: Claude can only use data provided in the prompt
3. **Explicit Uncertainty**: Claude must say "Based on provided data..." when uncertain
4. **Citation Validation**: DATA_CITATIONS section required in every response

Example Claude prompt constraint:
```
CRITICAL ANTI-HALLUCINATION RULES:
- You MUST cite ONLY the exact data values provided in the MARKET CONTEXT
- Every claim you make MUST reference a specific data point
- DO NOT invent data, metrics, or facts not provided in the input
```

## Logging and Transparency

All override decisions are logged to the database for audit:

```sql
CREATE TABLE oracle_predictions (
    id SERIAL PRIMARY KEY,
    bot_name VARCHAR(50),
    advice VARCHAR(50),
    win_probability REAL,
    confidence REAL,
    suggested_risk_pct REAL,
    suggested_sd_multiplier REAL,
    use_gex_walls BOOLEAN,
    reasoning TEXT,
    claude_validated BOOLEAN,
    claude_recommendation VARCHAR(50),
    claude_confidence_adj REAL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Configuration

Override behavior can be configured per bot:

```python
# ARES Configuration
STRATEGY_PRESETS = {
    StrategyPreset.MODERATE: {
        "vix_hard_skip": 32.0,      # Hard override threshold
        "risk_per_trade_pct": 10.0,  # Max risk (Oracle can suggest less)
        "sd_multiplier": 1.0,        # Default (Oracle can override)
    }
}
```

## Best Practices

1. **Always enable Claude validation** in production for additional safety layer
2. **Monitor override frequency** - High override rate may indicate ML model drift
3. **Review OVERRIDE decisions** - These represent significant disagreements
4. **Track win rates by recommendation type** to validate Claude's judgment
5. **Set appropriate VIX thresholds** based on bot strategy (directional vs neutral)

## Related Documentation

- [Circuit Breaker Integration](./CIRCUIT_BREAKER.md) - How circuit breakers interact with Oracle
- [Bot Trading Logic](./BOT_TRADING_LOGIC.md) - Entry/exit logic for each bot
- [ML Model Training](./ML_MODEL_TRAINING.md) - How the base models are trained
