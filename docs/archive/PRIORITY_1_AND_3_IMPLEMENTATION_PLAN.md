# Priority 1 & 3 Implementation Plan

## Overview

Implementing missing UIs for features that already log data + completing spread width tracking.

---

## Priority 1: Build UIs for Invisible Features

### Status Summary
These features LOG data but have no UI to view it:

| Feature | Data Logging | Backend API | Frontend UI | Priority |
|---------|--------------|-------------|-------------|----------|
| Probability System | ✅ Yes | ❌ No | ❌ No | **HIGH** |
| Conversation History | ✅ Yes | ❌ No | ❌ No | **HIGH** |
| OI Trends | ✅ Yes | ❌ No | ❌ No | **MEDIUM** |
| Recommendations History | ✅ Yes | ❌ No | ❌ No | **MEDIUM** |
| Push Subscriptions | ✅ Yes | ⚠️ Partial | ❌ No | **LOW** |
| GEX History | ✅ Job Created | ❌ No | ❌ No | **HIGH** |

---

## Implementation Plan

### Phase 1: Backend APIs (2-3 hours)

**File:** `backend/main.py`

Add endpoints:

1. **Probability System** (Lines ~6400+)
```python
@app.get("/api/probability/outcomes")
async def get_probability_outcomes(days: int = 30):
    """Get prediction accuracy over time"""

@app.get("/api/probability/weights")
async def get_probability_weights():
    """Get current probability weights"""

@app.get("/api/probability/calibration-history")
async def get_calibration_history(days: int = 90):
    """Get model calibration adjustments over time"""
```

2. **Conversation History** (Lines ~6450+)
```python
@app.get("/api/ai/conversations")
async def get_conversation_history(limit: int = 50):
    """Get AI copilot conversation history"""

@app.get("/api/ai/conversation/{conversation_id}")
async def get_conversation_detail(conversation_id: int):
    """Get full conversation thread"""
```

3. **OI Trends** (Lines ~6500+)
```python
@app.get("/api/oi/trends")
async def get_oi_trends(symbol: str = "SPY", days: int = 30):
    """Get historical open interest trends"""

@app.get("/api/oi/unusual-activity")
async def get_unusual_oi_activity(days: int = 7):
    """Detect unusual OI changes"""
```

4. **Recommendations History** (Lines ~6550+)
```python
@app.get("/api/recommendations/history")
async def get_recommendations_history(days: int = 30):
    """Get past trade recommendations"""

@app.get("/api/recommendations/performance")
async def get_recommendation_performance():
    """How well did past recommendations perform?"""
```

5. **GEX History** (Lines ~6600+)
```python
@app.get("/api/gex/history")
async def get_gex_history(symbol: str = "SPY", days: int = 30):
    """Get historical GEX snapshots"""

@app.get("/api/gex/regime-changes")
async def get_gex_regime_changes(days: int = 90):
    """When did GEX regime flip?"""
```

### Phase 2: Frontend UIs (8-10 hours)

#### 1. Probability Dashboard (`/probability`)

**File:** `frontend/src/app/probability/page.tsx`

**Components:**
- **Accuracy Chart**: Line chart showing prediction accuracy over time
- **Current Weights Table**: Display all probability weights with sliders to adjust
- **Calibration History**: Chart showing how model improved
- **Recent Outcomes**: Table of recent predictions vs actuals

**Est. Time:** 2 hours

---

#### 2. Conversation History (`/ai/history`)

**File:** `frontend/src/app/ai/history/page.tsx`

**Components:**
- **Conversation List**: Card grid of recent conversations
- **Search/Filter**: By date, topic, outcome
- **Conversation Detail**: Full chat thread with timestamps
- **Export**: Download conversation as JSON/MD

**Est. Time:** 1.5 hours

---

#### 3. OI Trends (`/oi/trends`)

**File:** `frontend/src/app/oi/trends/page.tsx`

**Components:**
- **OI Timeline Chart**: Historical open interest over time
- **Strike Heatmap**: OI distribution across strikes
- **Unusual Activity Alerts**: Highlight significant OI changes
- **Call/Put Ratio**: Track sentiment shifts

**Est. Time:** 2 hours

---

#### 4. Recommendations History (`/recommendations/history`)

**File:** `frontend/src/app/recommendations/history/page.tsx`

**Components:**
- **Recommendation Cards**: Past recommendations with outcomes
- **Performance Stats**: Win rate, avg return, confidence accuracy
- **Filter by Strategy**: Iron Condor, Straddle, etc.
- **Confidence Calibration**: Are 80% confident recs actually 80% accurate?

**Est. Time:** 1.5 hours

---

#### 5. GEX History (`/gex/history`)

**File:** `frontend/src/app/gex/history/page.tsx`

**Components:**
- **Net GEX Timeline**: Chart showing GEX over time
- **Flip Point Tracking**: When price crossed zero gamma
- **Regime Changes**: Highlight positive→negative transitions
- **Correlation with SPY**: Overlay price movement

**Est. Time:** 2 hours

---

#### 6. Notification Settings (`/settings/notifications`)

**File:** `frontend/src/app/settings/notifications/page.tsx`

**Components:**
- **Active Subscriptions**: List of devices subscribed
- **Subscribe/Unsubscribe**: Manage push notifications
- **Notification Preferences**: Which events to notify about
- **Test Notification**: Send test push

**Est. Time:** 1 hour

---

### Phase 3: Priority 3 - Spread Width Tracking

**File:** `autonomous_paper_trader.py`

**Function:** `_log_spread_width_performance()` (new function after line 2100)

```python
def _log_spread_width_performance(self, trade: Dict, option_data: Dict,
                                  contracts: int, entry_price: float,
                                  position_id: int):
    """
    Log spread width performance for iron condors

    Tracks:
    - Short call/put strikes
    - Long call/put strikes (protective wings)
    - Width of call spread vs put spread
    - Credit collected per dollar of width
    - Optimal widths by VIX regime
    """
    try:
        strategy = trade.get('strategy', '')

        # Only track spread strategies
        if strategy != 'IRON_CONDOR':
            return

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Extract spread details
        spot = option_data.get('spot_price', 0)

        # For iron condor: 4 strikes
        short_call = trade.get('short_call_strike', 0)
        long_call = trade.get('long_call_strike', 0)
        short_put = trade.get('short_put_strike', 0)
        long_put = trade.get('long_put_strike', 0)

        # Calculate widths
        call_spread_width = long_call - short_call
        put_spread_width = short_put - long_put
        total_width = call_spread_width + put_spread_width

        # Width as % of spot
        call_width_pct = (call_spread_width / spot) * 100
        put_width_pct = (put_spread_width / spot) * 100

        # Credit per dollar of risk
        max_loss = call_spread_width * 100 * contracts  # Assuming equal widths
        credit_collected = entry_price * contracts * 100
        credit_to_risk_ratio = credit_collected / max_loss if max_loss > 0 else 0

        # Get VIX regime
        vix = self._get_vix()
        if vix < 15:
            vix_regime = 'LOW'
        elif vix < 25:
            vix_regime = 'NORMAL'
        else:
            vix_regime = 'HIGH'

        # Calculate DTE
        exp_date_obj = datetime.strptime(trade.get('expiration'), '%Y-%m-%d')
        dte = (exp_date_obj - datetime.now()).days

        # Insert into spread_width_performance
        c.execute('''
            INSERT INTO spread_width_performance (
                position_id, entry_time, strategy_name, symbol,
                spot_price_at_entry, vix_at_entry, vix_regime, dte,
                short_call_strike, long_call_strike, call_spread_width, call_width_pct,
                short_put_strike, long_put_strike, put_spread_width, put_width_pct,
                total_wing_width, credit_collected, max_loss, credit_to_risk_ratio,
                contracts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            position_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            strategy,
            'SPY',
            spot,
            vix,
            vix_regime,
            dte,
            short_call,
            long_call,
            call_spread_width,
            call_width_pct,
            short_put,
            long_put,
            put_spread_width,
            put_width_pct,
            total_width,
            credit_collected,
            max_loss,
            credit_to_risk_ratio,
            contracts
        ))

        conn.commit()
        conn.close()

        self.log_action(
            'SPREAD_WIDTH',
            f"Logged spread width: Call ${call_spread_width:.0f}, Put ${put_spread_width:.0f} "
            f"(Credit/Risk: {credit_to_risk_ratio:.2%})",
            success=True
        )

    except Exception as e:
        self.log_action(
            'SPREAD_WIDTH_ERROR',
            f"Failed to log spread width: {str(e)}",
            success=False
        )
```

**Integration Points:**

1. Call from `_execute_iron_condor()` after trade execution
2. Update on position close with actual P&L
3. Add to optimizer analysis for "optimal width by VIX" insights

**Est. Time:** 2 hours

---

## Total Estimated Time

- **Backend APIs**: 3 hours
- **Frontend UIs**: 10 hours
- **Spread Width Tracking**: 2 hours
- **Testing & Integration**: 2 hours

**Total:** ~17 hours of development

---

## Deliverables

### Backend (`backend/main.py`)
- [ ] 5 new API endpoint groups (15 endpoints total)
- [ ] Query optimization for historical data
- [ ] Error handling and validation

### Frontend
- [ ] 6 new UI pages
- [ ] Navigation links updated
- [ ] API client methods added
- [ ] Charts and visualizations
- [ ] Responsive design

### Data Logging
- [ ] GEX history snapshot job
- [ ] Spread width tracking function
- [ ] Integration into autonomous trader

---

## Success Criteria

After implementation:
- ✅ All 22 empty tables have clear status (active, deprecated, or planned)
- ✅ No features "log data but can't be viewed"
- ✅ Users can see probability accuracy, conversation history, OI trends, etc.
- ✅ Spread width optimization data feeds into AI strategy optimizer
- ✅ GEX history enables backtesting against historical regimes

---

## Next Steps

1. Implement backend APIs (start with probability + GEX history)
2. Build frontend UIs (start with highest value: probability dashboard)
3. Add spread width tracking to autonomous trader
4. Test end-to-end data flow
5. Update navigation to include new pages
6. Document new features

**This transforms 11 "invisible" features into fully functional, valuable tools.**
