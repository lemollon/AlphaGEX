# GIDEON Bot Requirements

## Overview

**GIDEON** is an aggressive directional spreads trading bot, duplicated from SOLOMON with relaxed trading parameters to give it more room to trade.

| Field | Value |
|-------|-------|
| **Name** | GIDEON |
| **Full Name** | GIDEON Aggressive Directional |
| **Description** | Aggressive GEX-Based Directional Spreads |
| **Strategy** | Aggressive Directional Spread Trading |
| **Category** | Live Trading |
| **Based On** | SOLOMON (duplicate, not refactor) |

---

## Backend Configuration

### Aggressive Parameters (vs SOLOMON baseline)

| Parameter | SOLOMON | GIDEON | Rationale |
|-----------|--------|--------|-----------|
| `wall_filter_pct` | 3.0% | **10.0%** | Most relaxed - room to trade far from walls |
| `min_win_probability` | 48% | **40%** | Lower bar = more opportunities |
| `min_rr_ratio` | 0.8 | **0.5** | Accept marginal setups |
| `risk_per_trade_pct` | 2% | **4%** | Larger positions |
| `max_daily_trades` | 5 | **10** | Double the trading frequency |
| `max_open_positions` | 3 | **5** | More concurrent exposure |
| `spread_width` | $2 | **$3** | Slightly wider spreads |
| `profit_target_pct` | 50% | **30%** | Take profits earlier |
| `stop_loss_pct` | 50% | **70%** | Wider stops, let trades breathe |
| `ticker` | SPY | SPY | Same underlying |
| `capital` | $100K | $100K | Same starting capital |
| `entry_start` | 08:35 | 08:35 | Same trading window |
| `entry_end` | 14:30 | 14:30 | Same trading window |
| `force_exit` | 15:55 | 15:55 | Same force exit |

---

## Frontend Branding

### Color Scheme: Orange (Gideon flying toward the sun)

```typescript
GIDEON: {
  name: 'GIDEON',
  fullName: 'GIDEON Aggressive Directional',
  description: 'Aggressive GEX-Based Directional Spreads',
  strategy: 'Aggressive Directional Spread Trading',
  // Primary - Orange (bold, aggressive)
  primaryColor: 'orange',
  primaryBg: 'bg-orange-600',
  primaryBorder: 'border-orange-500',
  primaryText: 'text-orange-400',
  // Light variants
  lightBg: 'bg-orange-900/20',
  lightText: 'text-orange-300',
  lightBorder: 'border-orange-700/50',
  // Chart colors
  chartLine: 'stroke-orange-400',
  chartFill: 'fill-orange-500/20',
  chartPositive: 'text-orange-400',
  chartNegative: 'text-orange-600',
  // Position cards
  positionBorder: 'border-orange-600/50',
  positionBg: 'bg-orange-950/30',
  positionAccent: 'bg-orange-500',
  // Badges
  badgeBg: 'bg-orange-900/50',
  badgeText: 'text-orange-300',
  // Gradient
  icon: Flame,
  gradientFrom: 'from-orange-500',
  gradientTo: 'to-orange-900',
  // Hex for Recharts
  hexPrimary: '#F97316',
  hexLight: '#FDBA74',
  hexDark: '#EA580C',
}
```

### Navigation Entry

```typescript
{ href: '/gideon', label: 'GIDEON (Aggressive Directional)', icon: Flame, category: 'Live Trading' },
```

---

## Frontend Features (Full Parity with SOLOMON)

### Tabs (5 Tabs)

| Tab | Icon | Content |
|-----|------|---------|
| **Portfolio** | Wallet | Status Banner + Open Positions + Equity Curve |
| **Overview** | LayoutDashboard | Bot status grid (mode, ticker, window, scans) |
| **Activity** | Activity | Scan Activity Feed with Prophet decisions |
| **History** | History | Closed positions + CSV export |
| **Config** | Settings | Configuration values + Reset button |

### Components Required

| Feature | Component | Description |
|---------|-----------|-------------|
| Branded Header | `BotPageHeader` | Orange gradient, Flame icon, active status |
| Status Banner | `BotStatusBanner` | Real-time activity pulse, last scan |
| Quick Stats Row | `StatCard` x5 | Capital, P&L, Win Rate, Trades, Open |
| Equity Curve Chart | `EquityCurveChart` | Interactive chart with orange colors |
| Open Positions | `PositionCard` | Expandable with entry context |
| Closed Positions | `PositionCard` | Full exit details, P&L |
| CSV Export | Button | Export trades to CSV |
| Scan Activity Feed | `ScanActivityFeed` | Real-time decisions |
| Reset Data | Button + confirm | Full data reset |

### Hooks Required (10 hooks)

| Hook | Purpose |
|------|---------|
| `useICARUSStatus` | Bot status, heartbeat |
| `useICARUSPositions` | Open + closed positions |
| `useICARUSPerformance` | Performance metrics |
| `useGideonConfig` | Current configuration |
| `useICARUSLivePnL` | Real-time P&L |
| `useICARUSSignals` | Generated signals |
| `useICARUSLogs` | Log entries |
| `useICARUSDecisions` | Decision history |
| `useICARUSOracleAdvice` | Prophet advice |
| `useScanActivityIcarus` | Scan activity feed |

---

## Backend Implementation

### Directory Structure

```
trading/gideon/
├── __init__.py          # Exports GideonTrader, GideonConfig
├── models.py            # GideonConfig, SpreadPosition, TradeSignal
├── db.py                # Database layer (gideon_positions table)
├── signals.py           # Signal generation (aggressive params)
├── executor.py          # Order execution
└── trader.py            # Main orchestrator + MathOptimizerMixin

backend/api/routes/gideon_routes.py  # API endpoints
```

### API Endpoints (13+ endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/gideon/status` | GET | Bot status + heartbeat |
| `/api/gideon/positions` | GET | All positions |
| `/api/gideon/positions/closed` | GET | Closed positions |
| `/api/gideon/performance` | GET | Performance stats |
| `/api/gideon/config` | GET | Current config |
| `/api/gideon/config` | POST | Update config |
| `/api/gideon/scan-activity` | GET | Scan activity feed |
| `/api/gideon/live-pnl` | GET | Live P&L |
| `/api/gideon/signals` | GET | Generated signals |
| `/api/gideon/logs` | GET | Bot logs |
| `/api/gideon/decisions` | GET | Decision history |
| `/api/gideon/prophet-advice` | GET | Prophet advice |
| `/api/gideon/reset` | POST | Reset all data |

### Database Tables

| Table | Purpose |
|-------|---------|
| `gideon_positions` | Position tracking |
| `gideon_config` | Bot configuration |
| `gideon_scan_activity` | Scan activity logs |
| `icarus_bot_log` | Detailed logging |

---

## Implementation Checklist

### Backend Tasks
- [ ] Duplicate `trading/solomon_v2/` → `trading/gideon/`
- [ ] Update `GideonConfig` with aggressive defaults
- [ ] Create `gideon_routes.py`
- [ ] Create `gideon_positions` DB table
- [ ] Create `gideon_scan_activity` DB table
- [ ] Add scan activity logger support for GIDEON
- [ ] Register routes in `backend/main.py`

### Frontend Tasks
- [ ] Add GIDEON to `BotName` type in `BotBranding.tsx`
- [ ] Add GIDEON to `BOT_BRANDS` (orange/Flame theme)
- [ ] Add GIDEON to `EquityCurveChart` color lookup
- [ ] Add to `Navigation.tsx` (Live Trading category)
- [ ] Create `/app/gideon/page.tsx`
- [ ] Create `/app/gideon/logs/page.tsx`
- [ ] Create 10 `useICARUS*` hooks in `useMarketData.ts`
- [ ] Add GIDEON fetchers to `apiClient`
- [ ] Add GIDEON API methods to `api.ts`

---

## Key Differentiators from SOLOMON

1. **10% GEX Wall Filter** - Trades allowed far from walls (vs 3%)
2. **40% Win Probability Threshold** - More trades pass filter (vs 48%)
3. **0.5 Risk/Reward Minimum** - Accepts tighter setups (vs 0.8)
4. **4% Risk Per Trade** - Double position sizing (vs 2%)
5. **10 Max Daily Trades** - Double frequency (vs 5)
6. **5 Max Open Positions** - More concurrent exposure (vs 3)
7. **$3 Spread Width** - Wider spreads (vs $2)
8. **30% Profit Target** - Earlier exits (vs 50%)
9. **70% Stop Loss** - Wider stops (vs 50%)

---

*Created: January 2025*
*Status: Requirements Approved*
