# ARGUS (0DTE Gamma Live) - Feature Requirements

## Overview

**ARGUS** - Named after the "all-seeing" giant with 100 eyes from Greek mythology. A real-time visualization of net gamma by strike with ML-powered probability predictions, momentum indicators, Claude AI commentary, and a feedback loop for continuous bot improvement.

**Symbol:** SPY 0DTE (all 5 weekly expirations: Mon, Tue, Wed, Thu, Fri)

---

## 1. Core Specifications

| Specification | Value |
|---------------|-------|
| **Name** | ARGUS (0DTE Gamma Live) |
| **Symbol** | SPY (0DTE only) |
| **Expirations** | 5 per week (Monday through Friday) |
| **Data Source** | Tradier API |
| **Chart Refresh Rate** | Every 60 seconds |
| **AI Commentary Refresh** | Every 5 minutes |
| **Chart Type** | Vertical bar chart - NET gamma only (single color, not call/put split) |
| **Strike Range** | Expected move ± 5 strikes outside |

---

## 2. Market Hours Handling

| Time Period | Behavior |
|-------------|----------|
| **Pre-Market (4:00am - 9:30am ET)** | Show live gamma data from Tradier |
| **Market Hours (9:30am - 4:00pm ET)** | Full real-time updates every 60 seconds |
| **After Hours (4:00pm - 8:00pm ET)** | Show "Last Known" data with timestamp, grayed out |
| **Overnight (8:00pm - 4:00am ET)** | Show previous day's final snapshot with "Market Closed" banner |

### Display When Market Closed
```
┌─────────────────────────────────────────────────────────────────┐
│  ⏸️ MARKET CLOSED - Showing last known data from 4:00 PM ET     │
│  Next update when pre-market opens at 4:00 AM ET               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Multi-Day Expiration Tabs

SPY has 0DTE expirations **every day** (Mon-Fri). Each day gets its own chart.

### Tab Layout
```
┌─────┬─────┬─────┬─────┬─────┐
│ MON │ TUE │ WED │ THU │ FRI │  ← Click to switch expiration
└─────┴─────┴─────┴─────┴─────┘
        ▲
    [ACTIVE - highlighted]
```

### Tab Behavior
| Feature | Description |
|---------|-------------|
| **Default Tab** | Today's expiration (auto-selected) |
| **Tab Indicator** | Badge showing time until expiration |
| **Past Expirations** | Grayed out, show final snapshot |
| **Future Expirations** | Show current gamma structure |
| **Active Tab** | Highlighted with accent color |

---

## 4. Data Requirements

### 4.1 Primary Data (Per Strike)

| Field | Description | Source |
|-------|-------------|--------|
| `strike` | Strike price | Tradier options chain |
| `net_gamma` | Net gamma at strike (calls + puts combined) | Calculated from Tradier Greeks |
| `spot_price` | Current SPY price | Tradier quotes |
| `expected_move` | ATM straddle implied move | Calculated from 0DTE ATM options |

### 4.2 Calculated Metrics (Per Strike)

| Metric | Description | Calculation |
|--------|-------------|-------------|
| `probability_landing` | Probability price lands at this strike | **Hybrid: ML model + gamma-weighted distance** |
| `gamma_change_pct` | % change since last refresh | `(current - previous) / previous * 100` |
| `gamma_roc_1min` | Rate of change (1-min) | `current - previous` with arrow indicator |
| `gamma_roc_5min` | Rate of change (5-min rolling) | `current - value_5_min_ago` |

### 4.3 Historical Data Storage

| Field | Description | Retention |
|-------|-------------|-----------|
| `gamma_history` | Array of gamma values per strike | Last 30 minutes (30 data points) |
| `timestamp` | Time of each snapshot | Per-minute timestamps |

---

## 5. Probability Calculation (Hybrid Approach)

### 5.1 Why Combine ML + Gamma-Weighted Distance?

**Combined approach provides both predictive power AND current market reality:**

1. **ML Model (60% weight)** - Historical patterns:
   - How gamma structures have resolved in the past
   - Learned relationships between gamma magnitude and price behavior
   - Accounts for VIX regime, day of week, etc.

2. **Gamma-Weighted Distance (40% weight)** - Real-time dynamics:
   - Current market positioning
   - How far price needs to move
   - Relative gamma concentration (magnet strength)

### 5.2 Hybrid Probability Formula

```python
# ML Component (60% weight) - from existing models
ml_probability = gex_probability_models.predict_magnet_attraction(strike, spot, gamma_structure)

# Distance Component (40% weight) - real-time calculation
distance_from_spot = abs(strike - spot_price)
gamma_magnitude = abs(net_gamma_at_strike)
total_gamma = sum(all_strike_gammas)

# Gamma-weighted probability (higher gamma = more likely to attract)
gamma_weight = gamma_magnitude / total_gamma

# Distance decay (further = less likely)
distance_decay = exp(-distance_from_spot / expected_move)

distance_probability = gamma_weight * distance_decay * 100

# Combined probability
combined_probability = (0.6 * ml_probability) + (0.4 * distance_probability)

# Normalize so all strikes sum to 100%
normalized_probability = combined_probability / sum(all_combined_probabilities) * 100
```

### 5.3 ML Models to Use

From `quant/gex_probability_models.py`:

| Model | Purpose | Weight |
|-------|---------|--------|
| `magnet_attraction_prob` | Probability price reaches nearest magnet | Primary |
| `pin_zone_prob` | Probability of staying between magnets | Secondary |
| `direction_prediction` | UP/DOWN/FLAT classification | Context |

---

## 6. Rate of Change Indicators

### 6.1 Display Components

| Timeframe | Value | Arrow | Color |
|-----------|-------|-------|-------|
| **1-min ROC** | `+2.3%` | `↑` | Green if positive, Red if negative |
| **5-min ROC** | `-5.1%` | `↓` | Green if positive, Red if negative |

### 6.2 Arrow Logic

```
↑↑  = ROC > +10% (strong increase)
↑   = ROC > 0% (increasing)
→   = ROC ≈ 0% (stable, within ±1%)
↓   = ROC < 0% (decreasing)
↓↓  = ROC < -10% (strong decrease)
```

### 6.3 Color Coding

| Condition | Color | Meaning |
|-----------|-------|---------|
| ROC > +10% | Bright Green | Gamma surging - strong magnet |
| ROC > 0% | Green | Gamma increasing |
| ROC ≈ 0% | Gray | Stable |
| ROC < 0% | Red | Gamma decreasing |
| ROC < -10% | Bright Red | Gamma collapsing - losing magnet strength |

---

## 7. Pinning Detection & Highlights

### 7.1 Top 3 Gamma Magnets

**Definition:** Strikes with highest absolute net gamma

**Display:**
- Gold border/highlight on bar
- "MAGNET #1", "MAGNET #2", "MAGNET #3" labels
- Larger bar or glow effect

### 7.2 Likely Pin Strike

**Definition:** Strike with highest probability + highest gamma + closest to spot

**Calculation:**
```python
pin_score = (probability * 0.4) + (gamma_rank * 0.3) + (proximity_score * 0.3)
likely_pin = strike_with_max_pin_score
```

**Display:**
- Special "PIN" badge
- Pulsing animation
- Different bar color (purple/gold)

### 7.3 Danger Zones

**Definition:** Strikes where gamma is shifting rapidly (high ROC)

**Thresholds:**
| Condition | Classification |
|-----------|----------------|
| 5-min ROC > +25% | "BUILDING" - gamma accumulating rapidly |
| 5-min ROC < -25% | "COLLAPSING" - gamma evaporating |
| 1-min ROC > +15% | "SPIKE" - sudden gamma surge |

**Display:**
- Warning icon (⚠️) on the bar
- Tooltip with explanation
- Yellow/orange highlight

---

## 8. Historical Context (Per Strike)

### 8.1 Mini Sparkline Per Strike

Show last 30 minutes of gamma history as a small sparkline chart below or within each bar.

| Element | Description |
|---------|-------------|
| **Type** | Mini line chart (sparkline) |
| **Data Points** | 30 (one per minute) |
| **Height** | 20-30px |
| **Width** | Width of bar |

### 8.2 Hover Tooltip History

On hover, show expanded view:
- Last 30 minutes as larger chart
- Min/Max gamma values
- Time of peak gamma
- Trend direction

---

## 9. Claude AI Commentary Panel

### 9.1 Overview

Real-time natural language market commentary generated by Claude AI every 5 minutes, providing actionable insights based on gamma structure.

### 9.2 Panel Features

| Feature | Description |
|---------|-------------|
| **Update Frequency** | Every 5 minutes |
| **Format** | Natural language market commentary |
| **Default View** | Collapsed - shows latest 2-3 updates inline |
| **Expanded View** | Pop-out modal for full history |
| **Scrollable** | Browse all historical updates |
| **Export** | Excel button to download log history |

### 9.3 Panel UI States

**Collapsed View (Inline):**
```
┌─────────────────────────────────────────────────────────────────┐
│ 🧠 ARGUS AI INTEL                              [↗ Expand] [📥]  │
├─────────────────────────────────────────────────────────────────┤
│ 12:35 - Gamma tight at 594, pin probability 35%...              │
│ 12:30 - Strike 596 building, watch for magnet shift...          │
└─────────────────────────────────────────────────────────────────┘
```

**Expanded View (Pop-out Modal):**
```
┌─────────────────────────────────────────────────────────────────────────┐
│ 🧠 ARGUS AI COMMENTARY                                        [X Close] │
├─────────────────────────────────────────────────────────────────────────┤
│ [📥 Export to Excel]                              [🔍 Search] [Collapse]│
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  🕐 12:35 PM ET - 5-Minute Update                                       │
│  ─────────────────────────────────────────                              │
│  📊 GAMMA STRUCTURE: Net gamma remains heavily concentrated at 594      │
│  (32%) with secondary magnet at 596 (18%). The spread is tightening    │
│  - likely pinning setup forming.                                        │
│                                                                         │
│  ⚡ KEY CHANGE: Strike 595 gamma surged +28% in last 5 min. Dealers     │
│  may be rolling positions ahead of afternoon session.                   │
│                                                                         │
│  🎯 PIN PREDICTION: 594 strike now showing 35% pin probability (up      │
│  from 28%). SPY currently at $594.15 - within pin zone.                 │
│                                                                         │
│  ⚠️ WATCH: Strike 596 entered "BUILDING" danger zone. If gamma          │
│  continues accumulating, could become new magnet.                       │
│                                                                         │
│  🤖 BOT CONTEXT: ARES Iron Condor safe - short strikes at 590/598      │
│  both outside current magnet range.                                     │
│                                                                         │
│  📈 OUTLOOK: Expect range-bound action 593.50-595.50 through 2pm.      │
│  Watch for breakout if 596 gamma accelerates.                           │
│                                                                         │
│  ───────────────────────────────────────────────────────────────────    │
│  🕐 12:30 PM ET - 5-Minute Update                                       │
│  ...                                                                    │
│  (scrollable)                                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.4 Data Captured for Claude Commentary

**Real-Time Metrics (every 5 min):**

| Data Point | Description |
|------------|-------------|
| `gamma_structure_summary` | "Net gamma concentrated at 594-596 with 45% of total" |
| `gamma_flip_detected` | "ALERT: Strike 595 flipped from POSITIVE to NEGATIVE gamma" |
| `gamma_regime_change` | "Overall gamma regime shifted from bullish to bearish" |
| `magnet_changes` | "Top magnet shifted from 595 to 594 in last 5 min" |
| `probability_shifts` | "Pin probability at 594 increased from 28% to 35%" |
| `roc_patterns` | "Strike 596 showing rapid gamma build (+32% in 5 min)" |
| `danger_zone_status` | "2 strikes now in danger zone vs 0 earlier" |
| `spot_vs_structure` | "Spot moved toward top magnet, now within $0.50" |
| `expected_move_update` | "Expected move contracted from ±$2.50 to ±$2.10" |

**Context for Commentary:**

| Data Point | Description |
|------------|-------------|
| `time_of_day` | Morning vs power hour behavior differs |
| `vix_level` | "VIX at 18.5, elevated from open" |
| `day_of_week` | Monday gamma vs Friday gamma different |
| `historical_pattern_match` | "Similar structure on 12/15 led to pin at 592" |
| `bot_position_status` | "ARES has open Iron Condor, wings at 590/598" |

### 9.5 Claude Commentary Prompt Template

```
You are ARGUS, the all-seeing gamma analyst for AlphaGEX. Generate a 5-minute market update based on the current 0DTE gamma structure.

Current Data:
- Spot: {spot_price}
- Top 3 Magnets: {magnets}
- Likely Pin: {likely_pin} ({pin_probability}%)
- Danger Zones: {danger_zones}
- 5-min Changes: {changes}
- VIX: {vix}
- Time: {current_time} ET
- Active Bots: {bot_positions}

Generate a concise update covering:
1. GAMMA STRUCTURE - Where is gamma concentrated?
2. KEY CHANGE - What changed in last 5 minutes?
3. PIN PREDICTION - Where is price likely to settle?
4. WATCH - Any danger zones or warnings?
5. BOT CONTEXT - Are active bot positions safe?
6. OUTLOOK - Expected price action next 30 min

Keep it actionable and trader-focused. Use emojis sparingly for visual scanning.
```

### 9.6 Export to Excel

| Column | Description |
|--------|-------------|
| `timestamp` | Time of commentary |
| `spot_price` | SPY price at time |
| `top_magnet` | #1 magnet strike |
| `likely_pin` | Predicted pin strike |
| `pin_probability` | Pin probability % |
| `danger_zones` | Active danger zones |
| `vix` | VIX level |
| `full_commentary` | Claude's full text |

---

## 10. Additional Features

### 10.1 Historical Replay

**Definition:** Replay historical gamma structures to learn patterns and compare to current

#### Features

| Feature | Description |
|---------|-------------|
| **Date Picker** | Select any historical date |
| **Time Slider** | Scrub through the trading day minute by minute |
| **Play/Pause** | Auto-play replay at configurable speed (1x, 2x, 5x, 10x) |
| **Compare Mode** | Side-by-side with current day |
| **Outcome Overlay** | Show what actually happened (close price, pin location) |

#### UI Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 📼 HISTORICAL REPLAY                                          [X Close] │
├─────────────────────────────────────────────────────────────────────────┤
│ Date: [Dec 15, 2024 ▼]    Time: 10:35 AM ET                            │
│ ◄◄  ◄  [▶ Play]  ►  ►►    Speed: [1x ▼]    [Compare to Today]          │
│ ├──────────────●────────────────────────────────────────────────────┤  │
│ 9:30                      10:35                                 4:00   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  [HISTORICAL GAMMA CHART AT SELECTED TIME]                              │
│                                                                         │
│  Top Magnet: 592  |  Pin: 591 (28%)  |  Spot: $591.45                  │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│ 📊 OUTCOME (End of Day):                                                │
│ Close: $591.23  |  Pinned at: 591  |  High: $593.10  |  Low: $590.50   │
│ Prediction was: ✅ CORRECT (within $0.25 of predicted pin)             │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Use Cases

| Use Case | Description |
|----------|-------------|
| **Pattern Study** | "Show me days with similar gamma structure to today" |
| **Learning** | Understand how gamma evolved → price action relationship |
| **Backtesting** | Validate if current strategy would have worked |
| **Comparison** | "At this time yesterday, gamma was at X - today it's at Y" |

#### Data Requirements

| Field | Retention |
|-------|-----------|
| **Full gamma snapshots** | 90 days rolling |
| **1-minute resolution** | Full trading day (9:30am - 4:00pm) |
| **Outcome data** | Close, high, low, pin location |
| **Commentary** | Historical Claude commentary |

---

### 10.2 Pattern Alerts

**Definition:** Alert when current gamma structure matches historical patterns

| Alert | Description |
|-------|-------------|
| **Pattern Match** | "This structure matches 3 previous days that led to 1%+ moves" |
| **Confidence** | Pattern match confidence score |
| **Historical Outcome** | What happened those days |

### 10.3 Bot Integration Panel

Show what each bot is doing based on current gamma:

```
┌─────────────────────────────────────────────────────────────────┐
│ 🤖 BOT STATUS                                                   │
├─────────────────────────────────────────────────────────────────┤
│ ARES: IC open 590/598 - ✅ SAFE (magnets at 594-596)           │
│ ATHENA: No position - Watching for breakout signal             │
│ PHOENIX: Long 595C - ⚠️ Near magnet, monitor closely           │
└─────────────────────────────────────────────────────────────────┘
```

### 10.4 Accuracy Dashboard

Track prediction accuracy over time:

| Metric | Description |
|--------|-------------|
| **Pin Accuracy** | % of times pin prediction was within $0.50 of close |
| **Direction Accuracy** | % of correct UP/DOWN/FLAT predictions |
| **Magnet Hit Rate** | % of times price touched top 3 magnets |
| **Rolling 30-Day** | Trailing accuracy metrics |

### 10.5 Confidence Meter

Visual indicator of model confidence:

```
Confidence: ████████░░ 78%
[Based on: VIX regime (good), Pattern match (strong), Data quality (high)]
```

### 10.6 Voice Alerts (Optional)

| Setting | Description |
|---------|-------------|
| **Enable/Disable** | User toggle |
| **Alert Types** | Magnet shift, Danger zone, Pin zone entry |
| **Voice** | Browser text-to-speech |

### 10.7 Mobile Push Notifications

Critical alerts pushed to phone:

| Alert | Priority |
|-------|----------|
| Magnet Shift | HIGH |
| Danger Zone Entry | MEDIUM |
| Pin Zone Entry | MEDIUM |
| Pattern Match | LOW |

### 10.8 Compare to Yesterday

Overlay yesterday's gamma at same time for context:

```
┌─────────────────────────────────────────────────────────────────┐
│ [Toggle] Show Yesterday's Gamma (dotted line overlay)           │
│                                                                 │
│ Today's magnet: 594 | Yesterday at this time: 592              │
│ Gamma 15% higher today vs yesterday                             │
└─────────────────────────────────────────────────────────────────┘
```

### 10.9 Volume Heatmap

Show where options volume is concentrated vs gamma:

| Feature | Description |
|---------|-------------|
| **Overlay** | Toggle volume heatmap on chart |
| **Color** | Intensity based on volume |
| **Insight** | "High volume at 595 but gamma concentrated at 594" |

### 10.10 IV Skew Indicator

Call IV vs Put IV directional sentiment:

```
IV Skew: PUTS +2.3% premium (bearish sentiment)
         ◄────●────────►
       PUTS          CALLS
```

---

## 11. Alerts System

### 11.1 Alert Thresholds

| Alert Type | Trigger | Priority |
|------------|---------|----------|
| **Gamma Flip** | Strike flips from positive to negative gamma (or vice versa) | HIGH |
| **Regime Change** | Overall gamma regime shifts (bullish→bearish or vice versa) | HIGH |
| **Gamma Spike** | Any strike gamma increases >50% in 5 min | HIGH |
| **Magnet Shift** | Top magnet changes to different strike | HIGH |
| **Pin Zone Entry** | Spot price enters ±0.5% of likely pin | MEDIUM |
| **Danger Zone** | Any strike ROC exceeds ±25% | MEDIUM |
| **Gamma Collapse** | Total gamma decreases >20% in 10 min | LOW |
| **Pattern Match** | Structure matches historical profitable pattern | MEDIUM |

### 11.2 Alert Display

- Toast notification in corner
- Sound (optional, user configurable)
- Alert log panel (collapsible)
- Badge count on notification icon
- Mobile push (if enabled)

### 11.3 Alert Format

```
[HIGH] 12:34:05 - Strike 595 gamma spiked +52% in 5 min
[MEDIUM] 12:35:10 - SPY entered pin zone near 594 strike
[HIGH] 12:36:00 - Top magnet shifted from 595 to 594
[MEDIUM] 12:37:00 - Pattern match: Similar to Dec 15 (closed at magnet)
```

---

## 12. Feedback Loop for Bot Learning

### 12.1 Purpose

Store all predictions and outcomes to continuously improve bot trading performance through machine learning feedback.

### 12.2 Data Flow

```
┌─────────────────┐
│ Live ARGUS Data │
│ (every minute)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Predictions    │────▶│   Store in DB   │
│ - Pin strike    │     │ (with timestamp)│
│ - Probabilities │     └────────┬────────┘
│ - Direction     │              │
└─────────────────┘              │
                                 │
         ┌───────────────────────┘
         │
         ▼ (at market close)
┌─────────────────┐
│  Actual Outcome │
│ - Close price   │
│ - High/Low      │
│ - Where pinned  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Compare & Score │
│ - Prediction    │
│   accuracy      │
│ - Which signals │
│   worked        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Feedback Table  │
│ (training data) │
└────────┬────────┘
         │
         ▼ (weekly)
┌─────────────────┐
│ Retrain Models  │
│ - Better probs  │
│ - Better pins   │
│ - Better signals│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Improved Bots  │
│ ARES, ATHENA,   │
│ PHOENIX, etc.   │
└─────────────────┘
```

### 12.3 What Gets Stored

| Data Category | Fields | Purpose |
|---------------|--------|---------|
| **Predictions** | Pin strike, probabilities, direction, magnets, danger zones | Track prediction accuracy |
| **Structure Snapshots** | Full gamma by strike every 5 min | Pattern recognition training |
| **Bot Decisions** | What bots did based on ARGUS data | Correlate decisions with outcomes |
| **Outcomes** | Actual close, high, low, pin location | Ground truth |
| **Commentary** | Claude's analysis text | NLP training data |
| **Accuracy Scores** | Per-prediction accuracy | Reward signal for learning |

### 12.4 Feedback Loop Schedule

| Frequency | Action |
|-----------|--------|
| **Every minute** | Store gamma snapshot |
| **Every 5 min** | Store prediction + Claude commentary |
| **Market close** | Calculate daily accuracy scores |
| **Daily** | Update rolling accuracy metrics |
| **Weekly** | Retrain probability models with new data |
| **Monthly** | Full model evaluation and tuning |

### 12.5 Bot Integration Points

| Bot | How ARGUS Feeds It |
|-----|-------------------|
| **ARES** | "Is my IC short strike safe from magnets?" |
| **ATHENA** | "Which direction has highest probability?" |
| **PHOENIX** | "Where should I target for 0DTE entry?" |
| **PROMETHEUS** | "What's the ML confidence for this structure?" |

---

## 13. UI/UX Design

### 13.1 Full Page Layout

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ARGUS (0DTE Gamma Live) - SPY                                    [🔔 3] [⚙️]   │
│  Spot: $594.23  |  Expected Move: ±$2.50  |  VIX: 18.5  |  🔄 60s  |  Pre-Mkt   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────┬─────┬─────┬─────┬─────┐                                                │
│  │ MON │ TUE │ WED │ THU │ FRI │  ← Expiration Tabs                             │
│  └─────┴─────┴─────┴─────┴─────┘                                                │
├───────────────────────────────────────────────────────────────┬─────────────────┤
│                                                               │  🧠 ARGUS AI    │
│      32%        18%        12%        8%         5%           │  INTEL          │
│     ┌──┐       ┌──┐       ┌──┐      ┌──┐       ┌──┐          │ ─────────────── │
│     │██│  PIN  │██│       │██│      │██│       │██│          │ 12:35 - Gamma   │
│     │██│   ▼   │██│       │██│  ⚠️  │██│       │██│          │ tight at 594... │
│     │██│       │██│       │██│      │██│       │██│          │                 │
│  ───┴──┴───────┴──┴───────┴──┴──────┴──┴───────┴──┴───       │ 12:30 - Strike  │
│     592  593   594   595   596   597   598   599              │ 596 building... │
│     ↑1%  ↓2%  ↑3% ↑↑8%   ↓5%   →0%   ↓1%   ↓2%  ← ROC       │                 │
│                                                               │ [↗ Pop][📥 XL]  │
├───────────────────────────────────────────────────────────────┴─────────────────┤
│  MAGNETS: 🥇 594 (32%) | 🥈 596 (18%) | 🥉 592 (12%)    CONFIDENCE: ████░ 78%   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ⚠️ DANGER ZONES: 596 BUILDING (+28%)  |  📊 PATTERN: Matches Dec 15 (pinned)   │
├─────────────────────────────────────────────────────────────────────────────────┤
│  🤖 BOTS: ARES IC 590/598 ✅ | ATHENA: Watching | PHOENIX: Long 595C ⚠️          │
├─────────────────────────────────────────────────────────────────────────────────┤
│  📊 Yesterday Comparison: [Toggle] Magnet was at 592 (-$2 from today)           │
├─────────────────────────────────────────────────────────────────────────────────┤
│  IV SKEW: PUTS +2.3% ◄──●────► CALLS    |    VOLUME: Concentrated at 595        │
├─────────────────────────────────────────────────────────────────────────────────┤
│  🚨 ALERTS [3]                                                         [View ▼] │
│  • 12:34 - [HIGH] Strike 594 gamma spiked +52%                                  │
│  • 12:33 - [HIGH] Top magnet shifted to 594                                     │
│  • 12:30 - [MED] Pattern match: Similar to Dec 15                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Color Scheme

| Element | Color | Hex |
|---------|-------|-----|
| Net Gamma Bars | Blue gradient | `#3B82F6` → `#1D4ED8` |
| Top Magnet (#1) | Gold | `#F59E0B` |
| Pin Strike | Purple | `#8B5CF6` |
| Danger Zone | Orange/Red | `#F97316` |
| Positive ROC | Green | `#22C55E` |
| Negative ROC | Red | `#EF4444` |
| Confidence High | Green | `#22C55E` |
| Confidence Low | Red | `#EF4444` |

### 13.3 Responsive Behavior

| Screen Size | Behavior |
|-------------|----------|
| Desktop (>1024px) | Full layout with all panels visible |
| Tablet (768-1024px) | Chart + collapsible side panels |
| Mobile (<768px) | Simplified chart, stacked panels, swipe for details |

---

## 14. Technical Architecture

### 14.1 Backend API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /api/argus/gamma` | GET | Current net gamma by strike |
| `GET /api/argus/history` | GET | Historical gamma (last 30 min) |
| `GET /api/argus/probability` | GET | ML-powered probability per strike |
| `GET /api/argus/alerts` | GET | Active alerts |
| `GET /api/argus/commentary` | GET | Latest Claude AI commentary |
| `POST /api/argus/commentary/generate` | POST | Trigger new commentary |
| `GET /api/argus/bots` | GET | Active bot positions |
| `GET /api/argus/accuracy` | GET | Prediction accuracy metrics |
| `GET /api/argus/patterns` | GET | Pattern match analysis |
| `GET /api/argus/export` | GET | Export data to Excel |
| `WS /api/argus/stream` | WS | Real-time updates |
| `GET /api/argus/replay` | GET | Historical replay data for date/time |
| `GET /api/argus/replay/dates` | GET | Available dates for replay |

### 14.2 Data Flow

```
Tradier API
     │
     ▼ (every 60s)
┌─────────────────┐
│ Data Fetcher    │ ← Fetch options chain + Greeks
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Gamma Calculator│ ← Calculate net gamma per strike
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ History Store   │ ← Store in DB (rolling 30 min in memory)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ML Probability  │ ← Run gex_probability_models
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ ROC Calculator  │ ← Calculate 1-min and 5-min ROC
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Pattern Matcher │ ← Compare to historical patterns
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Alert Engine    │ ← Check thresholds, generate alerts
└────────┬────────┘
         │
         ├─────────────────┐ (every 5 min)
         │                 ▼
         │         ┌─────────────────┐
         │         │ Claude AI       │ ← Generate commentary
         │         │ Commentary      │
         │         └────────┬────────┘
         │                  │
         ▼                  ▼
┌─────────────────────────────────────┐
│           API Response              │ ← Send to frontend
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         Feedback Store              │ ← Store for ML training
└─────────────────────────────────────┘
```

### 14.3 Frontend Components

| Component | Description |
|-----------|-------------|
| `ArgusPage.tsx` | Main page container |
| `NetGammaChart.tsx` | Main chart component (Recharts) |
| `ExpirationTabs.tsx` | Mon-Fri tab selector |
| `StrikeBar.tsx` | Individual bar with probability label |
| `GammaSparkline.tsx` | Mini history chart per strike |
| `ROCIndicator.tsx` | Rate of change arrow + value |
| `ClaudeCommentary.tsx` | AI commentary panel (collapsible/expandable) |
| `CommentaryModal.tsx` | Pop-out modal for full commentary |
| `AlertPanel.tsx` | Alert notifications and log |
| `MagnetBadge.tsx` | Top magnet indicator |
| `PinStrikeBadge.tsx` | Likely pin strike indicator |
| `DangerZone.tsx` | Danger zone warning |
| `BotStatusPanel.tsx` | Bot integration status |
| `AccuracyDashboard.tsx` | Prediction accuracy metrics |
| `ConfidenceMeter.tsx` | Model confidence indicator |
| `YesterdayComparison.tsx` | Yesterday overlay toggle |
| `IVSkewIndicator.tsx` | IV skew display |
| `VolumeHeatmap.tsx` | Volume overlay |
| `ExportButton.tsx` | Excel export functionality |
| `HistoricalReplay.tsx` | Historical replay modal with time slider |
| `ReplayControls.tsx` | Play/pause, speed controls, date picker |
| `CompareMode.tsx` | Side-by-side historical vs current |

### 14.4 State Management

```typescript
interface ArgusState {
  // Core data
  spot_price: number;
  expected_move: number;
  last_updated: string;
  market_status: 'pre_market' | 'open' | 'after_hours' | 'closed';

  // Expiration
  active_expiration: 'mon' | 'tue' | 'wed' | 'thu' | 'fri';
  expirations: ExpirationData[];

  // Strike data
  strikes: StrikeData[];
  magnets: Magnet[];
  likely_pin: number;
  danger_zones: DangerZone[];

  // Analytics
  confidence: number;
  pattern_match: PatternMatch | null;
  iv_skew: IVSkew;

  // AI
  commentary: CommentaryEntry[];

  // Bots
  bot_positions: BotPosition[];

  // Alerts
  alerts: Alert[];

  // Historical
  history: Record<number, GammaHistoryPoint[]>;
  yesterday: StrikeData[] | null;

  // Accuracy
  accuracy_metrics: AccuracyMetrics;
}

interface StrikeData {
  strike: number;
  net_gamma: number;
  probability: number;
  gamma_change_pct: number;
  roc_1min: number;
  roc_5min: number;
  is_magnet: boolean;
  magnet_rank: number | null;
  is_pin: boolean;
  is_danger: boolean;
  danger_type: 'BUILDING' | 'COLLAPSING' | 'SPIKE' | null;
  volume: number;
  call_iv: number;
  put_iv: number;
}

interface CommentaryEntry {
  timestamp: string;
  text: string;
  spot_price: number;
  top_magnet: number;
  likely_pin: number;
  pin_probability: number;
  danger_zones: string[];
  vix: number;
}
```

---

## 15. Database Schema

### 15.1 Core Tables

```sql
-- Store gamma snapshots for historical analysis
CREATE TABLE argus_snapshots (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
    expiration_date DATE NOT NULL,
    snapshot_time TIMESTAMP NOT NULL,
    spot_price DECIMAL(10,2) NOT NULL,
    expected_move DECIMAL(10,2) NOT NULL,
    vix DECIMAL(5,2),
    market_status VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store per-strike gamma data
CREATE TABLE argus_strikes (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER REFERENCES argus_snapshots(id) ON DELETE CASCADE,
    strike DECIMAL(10,2) NOT NULL,
    net_gamma DECIMAL(20,4) NOT NULL,
    call_gamma DECIMAL(20,4),
    put_gamma DECIMAL(20,4),
    probability DECIMAL(5,2),
    roc_1min DECIMAL(10,4),
    roc_5min DECIMAL(10,4),
    volume INTEGER,
    call_iv DECIMAL(5,2),
    put_iv DECIMAL(5,2),
    is_magnet BOOLEAN DEFAULT FALSE,
    magnet_rank INTEGER,
    is_pin BOOLEAN DEFAULT FALSE,
    is_danger BOOLEAN DEFAULT FALSE,
    danger_type VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store Claude AI commentary
CREATE TABLE argus_commentary (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER REFERENCES argus_snapshots(id),
    commentary_text TEXT NOT NULL,
    spot_price DECIMAL(10,2),
    top_magnet DECIMAL(10,2),
    likely_pin DECIMAL(10,2),
    pin_probability DECIMAL(5,2),
    danger_zones JSONB,
    vix DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store alerts
CREATE TABLE argus_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL,
    strike DECIMAL(10,2),
    message TEXT NOT NULL,
    priority VARCHAR(10) NOT NULL,
    triggered_at TIMESTAMP NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store predictions for feedback loop
CREATE TABLE argus_predictions (
    id SERIAL PRIMARY KEY,
    prediction_date DATE NOT NULL,
    expiration_date DATE NOT NULL,
    prediction_time TIMESTAMP NOT NULL,
    predicted_pin DECIMAL(10,2),
    pin_probability DECIMAL(5,2),
    predicted_direction VARCHAR(10),
    direction_confidence DECIMAL(5,2),
    top_magnets JSONB,
    danger_zones JSONB,
    pattern_match VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store actual outcomes for feedback loop
CREATE TABLE argus_outcomes (
    id SERIAL PRIMARY KEY,
    prediction_id INTEGER REFERENCES argus_predictions(id),
    outcome_date DATE NOT NULL,
    actual_close DECIMAL(10,2) NOT NULL,
    actual_high DECIMAL(10,2),
    actual_low DECIMAL(10,2),
    actual_pin_strike DECIMAL(10,2),
    pin_accuracy DECIMAL(5,2),
    direction_correct BOOLEAN,
    magnet_touched BOOLEAN,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store accuracy metrics
CREATE TABLE argus_accuracy (
    id SERIAL PRIMARY KEY,
    metric_date DATE NOT NULL,
    pin_accuracy_7d DECIMAL(5,2),
    pin_accuracy_30d DECIMAL(5,2),
    direction_accuracy_7d DECIMAL(5,2),
    direction_accuracy_30d DECIMAL(5,2),
    magnet_hit_rate_7d DECIMAL(5,2),
    magnet_hit_rate_30d DECIMAL(5,2),
    total_predictions INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_argus_snapshots_time ON argus_snapshots(snapshot_time);
CREATE INDEX idx_argus_snapshots_expiration ON argus_snapshots(expiration_date);
CREATE INDEX idx_argus_strikes_snapshot ON argus_strikes(snapshot_id);
CREATE INDEX idx_argus_commentary_time ON argus_commentary(created_at);
CREATE INDEX idx_argus_alerts_time ON argus_alerts(triggered_at);
CREATE INDEX idx_argus_predictions_date ON argus_predictions(prediction_date);
CREATE INDEX idx_argus_outcomes_date ON argus_outcomes(outcome_date);
```

---

## 16. Integration Points

### 16.1 Existing Code to Use

| File | Component | Usage |
|------|-----------|-------|
| `quant/gex_probability_models.py` | `CombinedSignal`, `magnet_attraction_prob` | Probability calculation |
| `data/tradier_data_fetcher.py` | `TradierDataFetcher.get_options_chain()` | Data source |
| `data/gex_calculator.py` | Gamma calculation utilities | Net gamma calculation |
| `core/intelligence_and_strategies.py` | `ClaudeIntelligence` | AI commentary |
| `frontend/src/lib/api.ts` | API client | Frontend data fetching |

### 16.2 New Files to Create

| File | Purpose |
|------|---------|
| `backend/api/routes/argus_routes.py` | All ARGUS API endpoints |
| `core/argus_engine.py` | Core ARGUS logic and calculations |
| `core/argus_commentary.py` | Claude AI commentary generator |
| `core/argus_feedback.py` | Feedback loop processor |
| `frontend/src/app/argus/page.tsx` | Main ARGUS page |
| `frontend/src/components/argus/*` | All ARGUS components |

---

## 17. End-to-End Testing Requirements

### 17.1 Testing Philosophy

This feature requires **comprehensive E2E testing** to ensure it works as a complete, production-ready feature - not just code that compiles.

### 17.2 Test Categories

#### 17.2.1 Unit Tests

| Test Area | Tests |
|-----------|-------|
| **Gamma Calculator** | Net gamma calculation, probability hybrid formula |
| **ROC Calculator** | 1-min ROC, 5-min ROC, arrow logic |
| **Pin Detection** | Pin score calculation, magnet ranking |
| **Danger Zone** | Threshold detection, classification |
| **Pattern Matcher** | Historical pattern matching |

#### 17.2.2 Integration Tests

| Test Area | Tests |
|-----------|-------|
| **Tradier API** | Data fetching, error handling, rate limits |
| **Database** | Snapshot storage, retrieval, cleanup |
| **Claude API** | Commentary generation, prompt handling |
| **ML Models** | Probability predictions, model loading |

#### 17.2.3 API Tests

| Endpoint | Tests |
|----------|-------|
| `GET /api/argus/gamma` | Returns correct structure, handles missing data |
| `GET /api/argus/probability` | Returns probabilities sum to 100% |
| `GET /api/argus/commentary` | Returns valid commentary |
| `GET /api/argus/alerts` | Returns alerts in correct priority order |
| `GET /api/argus/export` | Returns valid Excel file |

#### 17.2.4 Frontend Tests

| Component | Tests |
|-----------|-------|
| **ArgusPage** | Renders correctly, handles loading/error states |
| **NetGammaChart** | Displays bars, handles empty data |
| **ExpirationTabs** | Tab switching works, correct tab highlighted |
| **ClaudeCommentary** | Collapse/expand works, export button works |
| **Alerts** | Toast notifications appear, can dismiss |

#### 17.2.5 E2E Tests (Playwright/Cypress)

| Scenario | Steps |
|----------|-------|
| **Full Page Load** | Navigate to ARGUS, verify all components render |
| **Tab Switching** | Click each expiration tab, verify chart updates |
| **Auto Refresh** | Wait 60s, verify data updates |
| **Commentary Expand** | Click expand, verify modal opens, scroll works |
| **Export to Excel** | Click export, verify file downloads |
| **Alert Interaction** | Trigger alert, verify toast appears, dismiss it |
| **Market Closed State** | Mock closed market, verify correct message |
| **Pre-Market State** | Mock pre-market, verify data displays |

### 17.3 Test Data Requirements

| Data Type | Source |
|-----------|--------|
| **Mock Gamma Data** | Fixtures with realistic gamma structures |
| **Mock Tradier Response** | Recorded API responses |
| **Mock Claude Response** | Pre-generated commentary |
| **Historical Patterns** | Sample pattern match data |

### 17.4 Performance Tests

| Metric | Target | Test |
|--------|--------|------|
| **Page Load** | < 2 seconds | Lighthouse performance audit |
| **Chart Render** | < 500ms | Measure render time |
| **API Response** | < 300ms | Load test endpoints |
| **Memory Usage** | No leaks over 1hr | Monitor memory during auto-refresh |

### 17.5 Test Commands

```bash
# Unit tests
pytest tests/unit/test_argus_*.py -v

# Integration tests
pytest tests/integration/test_argus_*.py -v

# API tests
pytest tests/api/test_argus_routes.py -v

# Frontend component tests
cd frontend && npm run test:argus

# E2E tests
cd frontend && npm run test:e2e:argus

# Full test suite
./scripts/test_argus_full.sh
```

### 17.6 CI/CD Pipeline

```yaml
# .github/workflows/argus-tests.yml
name: ARGUS Tests
on:
  push:
    paths:
      - 'core/argus_*.py'
      - 'backend/api/routes/argus_routes.py'
      - 'frontend/src/app/argus/**'
      - 'frontend/src/components/argus/**'
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Backend Tests
        run: pytest tests/**/test_argus*.py
      - name: Run Frontend Tests
        run: cd frontend && npm test -- --grep argus
      - name: Run E2E Tests
        run: cd frontend && npm run test:e2e:argus
```

---

## 18. Acceptance Criteria

### 18.1 Must Have (MVP)

- [ ] Net gamma bar chart for SPY 0DTE
- [ ] Auto-refresh every 60 seconds
- [ ] Probability % displayed above each strike
- [ ] % gamma change since last refresh
- [ ] Rate of change with arrow and color (1-min and 5-min)
- [ ] Strike range = expected move ± 5 strikes
- [ ] Top 3 magnet highlights
- [ ] Likely pin strike indicator
- [ ] 5 expiration tabs (Mon-Fri)
- [ ] Pre-market data support
- [ ] Market closed state with last known data
- [ ] Claude AI commentary every 5 minutes
- [ ] Commentary panel (collapsible/expandable)
- [ ] Export to Excel button
- [ ] Basic alerts (gamma spike, magnet shift)
- [ ] All E2E tests passing

### 18.2 Should Have

- [ ] Historical sparkline per strike (30 min)
- [ ] Danger zone warnings
- [ ] Bot integration panel
- [ ] Accuracy dashboard
- [ ] Confidence meter
- [ ] Pattern alerts
- [ ] Yesterday comparison overlay
- [ ] Feedback loop storage

### 18.3 Nice to Have

- [ ] WebSocket for real-time updates
- [ ] Voice alerts (user configurable)
- [ ] Mobile push notifications
- [ ] Volume heatmap
- [ ] IV skew indicator
- [ ] Mobile-optimized view
- [ ] Historical Replay with time slider
- [ ] Historical Replay compare mode (side-by-side)

---

## 19. Success Metrics

| Metric | Target |
|--------|--------|
| **Page Load Time** | < 2 seconds |
| **Refresh Latency** | < 500ms per update |
| **Pin Prediction Accuracy** | > 60% within $0.50 of close |
| **Direction Accuracy** | > 55% correct |
| **Magnet Hit Rate** | > 70% touched during day |
| **User Engagement** | > 10 min avg session time |
| **Test Coverage** | > 80% code coverage |
| **E2E Test Pass Rate** | 100% on deploy |

---

## 20. Document Info

- **Feature Name:** ARGUS (0DTE Gamma Live)
- **Created:** 2024-12-21
- **Updated:** 2024-12-21
- **Status:** Requirements Complete - Awaiting Approval
- **Author:** AlphaGEX Team
- **Navigation Category:** Analysis
- **Next Step:** Implementation planning after user approval
