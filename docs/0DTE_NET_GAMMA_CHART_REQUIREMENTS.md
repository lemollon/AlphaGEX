# 0DTE Net Gamma Chart - Feature Requirements

## Overview

Real-time visualization of net gamma by strike with ML-powered probability predictions and momentum indicators to identify pinning zones and directional magnets for **SPY 0DTE only**.

---

## 1. Core Specifications

| Specification | Value |
|---------------|-------|
| **Symbol** | SPY (0DTE only) |
| **Data Source** | Tradier API |
| **Refresh Rate** | Every 60 seconds |
| **Chart Type** | Vertical bar chart - NET gamma only (not red/green call/put split) |
| **Strike Range** | Expected move ± 5 strikes outside |

---

## 2. Data Requirements

### 2.1 Primary Data (Per Strike)

| Field | Description | Source |
|-------|-------------|--------|
| `strike` | Strike price | Tradier options chain |
| `net_gamma` | Net gamma at strike (calls + puts combined) | Calculated from Tradier Greeks |
| `spot_price` | Current SPY price | Tradier quotes |
| `expected_move` | ATM straddle implied move | Calculated from 0DTE ATM options |

### 2.2 Calculated Metrics (Per Strike)

| Metric | Description | Calculation |
|--------|-------------|-------------|
| `probability_landing` | Probability price lands at this strike | **Hybrid: ML model + gamma-weighted distance** |
| `gamma_change_pct` | % change since last refresh | `(current - previous) / previous * 100` |
| `gamma_roc_1min` | Rate of change (1-min) | `current - previous` with arrow indicator |
| `gamma_roc_5min` | Rate of change (5-min rolling) | `current - value_5_min_ago` |

### 2.3 Historical Data Storage

| Field | Description | Retention |
|-------|-------------|-----------|
| `gamma_history` | Array of gamma values per strike | Last 30 minutes (30 data points) |
| `timestamp` | Time of each snapshot | Per-minute timestamps |

---

## 3. Probability Calculation (Hybrid Approach)

### 3.1 Why Combine ML + Gamma-Weighted Distance?

**Yes, it makes sense to combine because:**

1. **ML Model** captures historical patterns:
   - How gamma structures have resolved in the past
   - Learned relationships between gamma magnitude and price behavior
   - Accounts for VIX regime, day of week, etc.

2. **Gamma-Weighted Distance** captures real-time dynamics:
   - Current market positioning
   - How far price needs to move
   - Relative gamma concentration (magnet strength)

3. **Combined** gives both predictive power AND current market reality

### 3.2 Hybrid Probability Formula

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

### 3.3 ML Models to Use

From `quant/gex_probability_models.py`:

| Model | Purpose | Weight |
|-------|---------|--------|
| `magnet_attraction_prob` | Probability price reaches nearest magnet | Primary |
| `pin_zone_prob` | Probability of staying between magnets | Secondary |
| `direction_prediction` | UP/DOWN/FLAT classification | Context |

---

## 4. Rate of Change Indicators

### 4.1 Display Components

| Timeframe | Value | Arrow | Color |
|-----------|-------|-------|-------|
| **1-min ROC** | `+2.3%` | `↑` | Green if positive, Red if negative |
| **5-min ROC** | `-5.1%` | `↓` | Green if positive, Red if negative |

### 4.2 Arrow Logic

```
↑↑  = ROC > +10% (strong increase)
↑   = ROC > 0% (increasing)
→   = ROC ≈ 0% (stable, within ±1%)
↓   = ROC < 0% (decreasing)
↓↓  = ROC < -10% (strong decrease)
```

### 4.3 Color Coding

| Condition | Color | Meaning |
|-----------|-------|---------|
| ROC > +10% | Bright Green | Gamma surging - strong magnet |
| ROC > 0% | Green | Gamma increasing |
| ROC ≈ 0% | Gray | Stable |
| ROC < 0% | Red | Gamma decreasing |
| ROC < -10% | Bright Red | Gamma collapsing - losing magnet strength |

---

## 5. Pinning Detection & Highlights

### 5.1 Top 3 Gamma Magnets

**Definition:** Strikes with highest absolute net gamma

**Display:**
- Gold border/highlight on bar
- "MAGNET #1", "MAGNET #2", "MAGNET #3" labels
- Larger bar or glow effect

### 5.2 Likely Pin Strike

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

### 5.3 Danger Zones

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

## 6. Historical Context

### 6.1 Mini Sparkline Per Strike

Show last 30 minutes of gamma history as a small sparkline chart below or within each bar.

| Element | Description |
|---------|-------------|
| **Type** | Mini line chart (sparkline) |
| **Data Points** | 30 (one per minute) |
| **Height** | 20-30px |
| **Width** | Width of bar |

### 6.2 Hover Tooltip History

On hover, show expanded view:
- Last 30 minutes as larger chart
- Min/Max gamma values
- Time of peak gamma
- Trend direction

---

## 7. Alerts System

### 7.1 Alert Thresholds

| Alert Type | Trigger | Priority |
|------------|---------|----------|
| **Gamma Spike** | Any strike gamma increases >50% in 5 min | HIGH |
| **Magnet Shift** | Top magnet changes to different strike | HIGH |
| **Pin Zone Entry** | Spot price enters ±0.5% of likely pin | MEDIUM |
| **Danger Zone** | Any strike ROC exceeds ±25% | MEDIUM |
| **Gamma Collapse** | Total gamma decreases >20% in 10 min | LOW |

### 7.2 Alert Display

- Toast notification in corner
- Sound (optional, user configurable)
- Alert log panel (collapsible)
- Badge count on notification icon

### 7.3 Alert Format

```
[HIGH] 12:34:05 - Strike 595 gamma spiked +52% in 5 min
[MEDIUM] 12:35:10 - SPY entered pin zone near 594 strike
[HIGH] 12:36:00 - Top magnet shifted from 595 to 594
```

---

## 8. UI/UX Design

### 8.1 Chart Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  0DTE Net Gamma Chart - SPY                    Last: 12:34:05   │
│  Spot: $594.23  |  Expected Move: ±$2.50  |  [Auto-Refresh: ON] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│     32%        Probability labels above bars                    │
│    ┌──┐   18%                                                   │
│    │██│  ┌──┐   12%    8%     5%                               │
│    │██│  │██│  ┌──┐  ┌──┐  ┌──┐                                │
│    │██│  │██│  │██│  │██│  │██│   ← Net gamma bars             │
│    │██│  │██│  │██│  │██│  │██│                                │
│ ───┴──┴──┴──┴──┴──┴──┴──┴──┴──┴─────────────────────────────── │
│    591   592   593  *594*  595   596   597   598   599         │
│                       ▲                                         │
│                    SPOT PIN                                     │
│                                                                 │
│  ┌─ Per Strike Metrics ─────────────────────────────────────┐  │
│  │ Strike 594: Γ Change: +3.2% ↑  |  5min ROC: +8.1% ↑      │  │
│  │ [▁▂▃▄▅▆▇█▇▆] ← sparkline                                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  MAGNETS: #1 594 (32%) | #2 592 (18%) | #3 595 (12%)           │
│  DANGER:  596 ⚠️ Building (+28% 5min)                           │
├─────────────────────────────────────────────────────────────────┤
│  ALERTS [3]                                              [View] │
│  • 12:34 - Strike 594 gamma spiked +52%                        │
│  • 12:33 - Top magnet shifted to 594                           │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 Color Scheme

| Element | Color | Hex |
|---------|-------|-----|
| Net Gamma Bars | Blue gradient | `#3B82F6` → `#1D4ED8` |
| Top Magnet | Gold | `#F59E0B` |
| Pin Strike | Purple | `#8B5CF6` |
| Danger Zone | Orange/Red | `#F97316` |
| Positive ROC | Green | `#22C55E` |
| Negative ROC | Red | `#EF4444` |

### 8.3 Responsive Behavior

| Screen Size | Behavior |
|-------------|----------|
| Desktop (>1024px) | Full chart with all metrics visible |
| Tablet (768-1024px) | Chart with collapsible metrics panel |
| Mobile (<768px) | Simplified chart, swipe for details |

---

## 9. Technical Architecture

### 9.1 Backend API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/gamma/0dte/net` | GET | Current net gamma by strike |
| `/api/gamma/0dte/history` | GET | Historical gamma (last 30 min) |
| `/api/gamma/0dte/probability` | GET | ML-powered probability per strike |
| `/api/gamma/0dte/alerts` | GET | Active alerts |
| `/api/gamma/0dte/stream` | WS | Real-time updates (optional) |

### 9.2 Data Flow

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
│ History Store   │ ← Store in memory/Redis (30 min rolling)
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
│ Alert Engine    │ ← Check thresholds, generate alerts
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ API Response    │ ← Send to frontend
└─────────────────┘
```

### 9.3 Frontend Components

| Component | Description |
|-----------|-------------|
| `NetGammaChart.tsx` | Main chart component (Recharts/Plotly) |
| `StrikeBar.tsx` | Individual bar with probability label |
| `GammaSparkline.tsx` | Mini history chart per strike |
| `ROCIndicator.tsx` | Rate of change arrow + value |
| `AlertPanel.tsx` | Alert notifications and log |
| `MagnetBadge.tsx` | Top magnet indicator |
| `PinStrikeBadge.tsx` | Likely pin strike indicator |

### 9.4 State Management

```typescript
interface GammaChartState {
  spot_price: number;
  expected_move: number;
  last_updated: string;
  strikes: StrikeData[];
  magnets: Magnet[];
  likely_pin: number;
  danger_zones: DangerZone[];
  alerts: Alert[];
  history: Record<number, GammaHistoryPoint[]>;
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
}
```

---

## 10. Database Schema

### 10.1 New Tables

```sql
-- Store gamma snapshots for historical analysis
CREATE TABLE gamma_0dte_snapshots (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL DEFAULT 'SPY',
    snapshot_time TIMESTAMP NOT NULL,
    spot_price DECIMAL(10,2) NOT NULL,
    expected_move DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store per-strike gamma data
CREATE TABLE gamma_0dte_strikes (
    id SERIAL PRIMARY KEY,
    snapshot_id INTEGER REFERENCES gamma_0dte_snapshots(id),
    strike DECIMAL(10,2) NOT NULL,
    net_gamma DECIMAL(20,4) NOT NULL,
    call_gamma DECIMAL(20,4),
    put_gamma DECIMAL(20,4),
    probability DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Store alerts
CREATE TABLE gamma_0dte_alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL,
    strike DECIMAL(10,2),
    message TEXT NOT NULL,
    priority VARCHAR(10) NOT NULL,
    triggered_at TIMESTAMP NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_snapshots_time ON gamma_0dte_snapshots(snapshot_time);
CREATE INDEX idx_strikes_snapshot ON gamma_0dte_strikes(snapshot_id);
CREATE INDEX idx_alerts_time ON gamma_0dte_alerts(triggered_at);
```

---

## 11. Integration Points

### 11.1 Existing Code to Use

| File | Component | Usage |
|------|-----------|-------|
| `quant/gex_probability_models.py` | `CombinedSignal`, `magnet_attraction_prob` | Probability calculation |
| `data/tradier_data_fetcher.py` | `TradierDataFetcher.get_options_chain()` | Data source |
| `data/gex_calculator.py` | Gamma calculation utilities | Net gamma calculation |
| `frontend/src/lib/api.ts` | API client | Frontend data fetching |

### 11.2 New Route File

Create: `backend/api/routes/gamma_0dte_routes.py`

---

## 12. Acceptance Criteria

### 12.1 Must Have (MVP)

- [ ] Net gamma bar chart for SPY 0DTE
- [ ] Auto-refresh every 60 seconds
- [ ] Probability % displayed above each strike
- [ ] % gamma change since last refresh
- [ ] Rate of change with arrow and color (1-min and 5-min)
- [ ] Strike range = expected move ± 5 strikes
- [ ] Top 3 magnet highlights
- [ ] Likely pin strike indicator

### 12.2 Should Have

- [ ] Historical sparkline per strike (30 min)
- [ ] Danger zone warnings
- [ ] Alert notifications (toast)
- [ ] Alert log panel

### 12.3 Nice to Have

- [ ] WebSocket for real-time updates
- [ ] Sound alerts (user configurable)
- [ ] Export data to CSV
- [ ] Mobile-optimized view

---

## 13. Open Questions

1. **Tradier Rate Limits:** Need to verify 60-second refresh is within rate limits
2. **Market Hours Only:** Should chart disable/show message outside 9:30am-4:00pm ET?
3. **Pre-Market:** Include pre-market gamma data (4:00am-9:30am)?
4. **Multiple 0DTE:** On days with multiple 0DTE expirations (Mon/Wed/Fri), which to show?

---

## 14. Success Metrics

| Metric | Target |
|--------|--------|
| Page Load Time | < 2 seconds |
| Refresh Latency | < 500ms per update |
| Probability Accuracy | Track vs actual close location |
| User Engagement | Time on page, refresh clicks |

---

## Document Info

- **Created:** 2024-12-21
- **Status:** Requirements Complete - Awaiting Approval
- **Author:** AlphaGEX Team
- **Next Step:** Implementation planning after user approval
