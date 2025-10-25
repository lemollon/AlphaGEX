# AlphaGEX Enhancement Integration Guide

## Overview
This document explains the three major enhancements added to AlphaGEX for improved profitability:

1. **Expiration Dates on All Strategies** - Real dates, not just "7-14 DTE"
2. **SPY Paper Trading with Auto-Execution** - Test strategies with automated trading
3. **Weekly Gamma Tracking** - Track intraday gamma changes for better strategy timing

## Files Created

### 1. Expiration System
- **`expiration_utils.py`** - Calculate actual expiration dates from DTE targets
  - `get_next_expiration(dte_target)` - Get Friday/Monthly expiration
  - `add_expiration_to_setup(setup)` - Add dates to strategy setups
  - `format_expiration_display()` - Format for UI

### 2. Paper Trading System
- **`paper_trader.py`** - Full paper trading engine with auto-execution
  - `PaperTradingEngine` - Core trading engine
  - `open_position()` / `close_position()` - Position management
  - `auto_manage_positions()` - Auto exit based on conditions
  - `evaluate_new_setup()` - Decide if setup should be executed
  - Database tables: `paper_positions`, `paper_performance`, `paper_config`

- **`paper_trading_dashboard.py`** - UI for paper trading
  - Performance metrics (P&L, win rate, etc.)
  - Open positions view with expiration countdown
  - Trade history
  - Settings (enable/disable, capital, min confidence, etc.)

### 3. Gamma Tracking System
- **`gamma_tracking_database.py`** - Historical gamma database
  - `GammaTrackingDB` - Store/retrieve gamma snapshots
  - `store_gamma_snapshot()` - Save current state
  - `calculate_daily_summary()` - Daily aggregations
  - `calculate_spy_correlation()` - Correlation with SPY
  - Database tables: `gamma_history`, `gamma_daily_summary`, `spy_correlation`

## Integration Steps

### Step 1: Add to Main App (`gex_copilot.py`)

Add imports at the top:
```python
from paper_trader import PaperTradingEngine
from gamma_tracking_database import GammaTrackingDB
from paper_trading_dashboard import (
    display_paper_trading_dashboard_page,
    display_auto_execute_panel,
    display_gamma_tracking_integration
)
from expiration_utils import add_expiration_to_setup, display_expiration_info
```

Initialize in `main()` function session state:
```python
if 'paper_trading_engine' not in st.session_state:
    st.session_state.paper_trading_engine = PaperTradingEngine()
if 'gamma_tracking_db' not in st.session_state:
    st.session_state.gamma_tracking_db = GammaTrackingDB()
```

Add new tab to the tabs list (line ~409):
```python
tabs = st.tabs([
    "📈 GEX Analysis",
    "🎯 Trade Setups",
    "🔍 Multi-Symbol Scanner",
    "🔔 Alerts",
    "📅 Trading Plans",
    "💬 AI Co-Pilot",
    "📊 Positions",
    "📔 Trade Journal",
    "🤖 Paper Trader",  # NEW
    "📅 Gamma Tracking",  # NEW
    "📚 Education"
])
```

### Step 2: Enhance Trade Setups Tab

In the "🎯 Trade Setups" tab (tabs[1]), add expiration display for each setup:

```python
# After detecting setups
for setup in setups:
    # Add expiration information
    setup = add_expiration_to_setup(setup)

    # Display setup with expiration
    st.markdown(f"### {setup['strategy']}")
    display_expiration_info(setup)  # Shows expiration, type, countdown

    # Rest of setup display...
```

Add auto-execute evaluation at the end of Trade Setups tab:
```python
# At the end of tabs[1]
if st.session_state.current_data:
    gex_data = st.session_state.current_data.get('gex', {})
    display_auto_execute_panel(setups, gex_data)
```

### Step 3: Add Paper Trading Tab

Add a new tab section (after Trade Journal tab):

```python
# Paper Trading Tab
with tabs[8]:  # Adjust index based on your tab order
    display_paper_trading_dashboard_page()
```

### Step 4: Add Gamma Tracking Tab

Add another new tab section:

```python
# Gamma Tracking Tab
with tabs[9]:  # Adjust index based on your tab order
    if st.session_state.current_data:
        current_symbol = st.session_state.current_data.get('symbol', 'SPY')
        display_gamma_tracking_integration(current_symbol)
    else:
        st.info("Select a symbol to start gamma tracking")
```

### Step 5: Auto-Capture Gamma Snapshots

In the "Refresh Symbol" button handler (sidebar), add:

```python
# After fetching GEX data successfully
if gex_data and not gex_data.get('error'):
    # Store gamma snapshot for tracking
    skew_data = st.session_state.api_client.get_skew_data(symbol)
    st.session_state.gamma_tracking_db.store_gamma_snapshot(
        symbol, gex_data, skew_data
    )

    # Calculate daily summary if needed
    today = datetime.now().strftime('%Y-%m-%d')
    st.session_state.gamma_tracking_db.calculate_daily_summary(symbol, today)

    # Calculate SPY correlation if not SPY
    if symbol != 'SPY':
        st.session_state.gamma_tracking_db.calculate_spy_correlation(symbol, today)
```

### Step 6: Auto-Manage Paper Positions

Add a scheduled check in the sidebar or as a background task:

```python
# In sidebar or main area
if st.session_state.paper_trading_engine.is_auto_execute_enabled():
    # Auto-manage positions
    actions = st.session_state.paper_trading_engine.auto_manage_positions(
        st.session_state.api_client
    )

    if actions:
        # Show notifications
        for action in actions:
            st.sidebar.success(f"Paper Trade: {action['action']} {action['symbol']}")
```

## Usage Instructions

### For Expiration Dates:
1. All strategy setups now automatically include actual expiration dates
2. View expiration countdown in "Open Positions" and "Trade Setups" tabs
3. Expirations are calculated based on next Friday (weeklies) or third Friday (monthlies)

### For Paper Trading:
1. Go to "Paper Trader" tab
2. Click "Settings" subtab
3. Enable "Paper Trading" and "Auto-Execute"
4. Set capital, minimum confidence (recommend 70%+), and max position size
5. System will automatically:
   - Execute high-confidence setups from "Trade Setups"
   - Update position values throughout the day
   - Close positions based on profit targets, stop losses, or expiration
   - Track performance metrics

### For Gamma Tracking:
1. Go to "Gamma Tracking" tab or use auto-capture
2. Click "Capture Snapshot" throughout the day
3. View intraday changes, weekly trends, and SPY correlation
4. Use insights to improve entry/exit timing

## Database Schema

### paper_positions
- Track all paper trades (open and closed)
- Includes expiration dates, P&L, exit reasons

### gamma_history
- Intraday snapshots of gamma data
- Stores price, GEX, flip, walls, IV, PCR

### gamma_daily_summary
- Daily aggregations of gamma data
- Open/close GEX, high/low, changes

### spy_correlation
- Daily correlation scores between symbols and SPY
- Price and GEX correlation tracking

## Performance Goals

With these enhancements:
- **Better Timing**: Weekly gamma patterns reveal optimal entry times
- **Better Exits**: Auto-close on profit targets (50%+) or stops (-30%)
- **Better Selection**: Only trade 70%+ confidence setups
- **Better Data**: Real expiration dates for accurate Greeks
- **Better Tracking**: Paper trade to validate before going live

Target: **75%+ win rate** with proper setup selection and timing
