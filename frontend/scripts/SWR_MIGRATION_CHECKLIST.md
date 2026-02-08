# SWR Migration Checklist for AlphaGEX

## Overview
This document tracks the migration of all AlphaGEX pages from useState/useEffect data fetching to SWR hooks for persistent caching and instant page loads.

## Pre-Migration Setup
- [x] Install SWR library (`npm install swr`)
- [x] Create `/lib/hooks/useMarketData.ts` with SWR hooks (50+ hooks)
- [x] Update `ClientProviders.tsx` with SWRConfig and prefetching
- [x] Create E2E test file (`swr-caching.spec.ts`)

---

## Dashboard Components (COMPLETED)
| Component | Status | Hooks Used |
|-----------|--------|------------|
| MarketCommentary.tsx | ✅ Done | useMarketCommentary |
| DailyTradingPlan.tsx | ✅ Done | useDailyTradingPlan |
| GammaExpirationWidget.tsx | ✅ Done | useGammaExpiration |

---

## Page Migration Status

### Trading Bot Pages
| Page | Status | Hooks Used | Notes |
|------|--------|------------|-------|
| /vix | ✅ Done | useVIX, useVIXHedgeSignal, useVIXSignalHistory | VIX dashboard with cached hedge signals |
| /ares | ✅ Done | useARESStatus, useARESPerformance, useARESEquityCurve, useARESPositions, useARESMarketData, useARESTradierStatus, useARESConfig | Iron Condor bot with full caching |
| /solomon | ✅ Done | useATHENAStatus, useATHENAPositions, useATHENASignals, useATHENAPerformance, useATHENAOracleAdvice, useATHENAMLSignal, useATHENALogs | Directional spread bot with caching |
| /trader | ⏳ Pending | Hooks available | Uses existing trader hooks |

### Analytics Pages
| Page | Status | Hooks Used | Notes |
|------|--------|------------|-------|
| /gamma | ✅ Done | useVIX (VIX data), existing cache | VIX data now via SWR, gamma uses WebSocket |
| /gex | ⏳ Pending | Hooks available | useGEX, useGEXLevels, useGEXHistory |
| /ml | ⏳ Pending | Hooks available | useMLStatus, useMLFeatureImportance |
| /prophet | ✅ Done | useProphetStatus, useOracleLogs, useOraclePredictions | Prophet AI predictions with caching |

### System Pages
| Page | Status | Hooks Used | Notes |
|------|--------|------------|-------|
| /database | ⏳ Pending | Hooks available | useDatabaseStats, useTableFreshness, useSystemHealth |
| /logs | ✅ Done | useLogsSummary, useMLLogs, useOraclePredictions, useAutonomousLogs | Master logs dashboard with caching |
| /alerts | ⏳ Pending | Hooks available | useAlerts, useAlertHistory |
| /scanner | ⏳ Pending | Hooks available | useScannerHistory |

### Wheel Strategy Pages
| Page | Status | Hooks Used | Notes |
|------|--------|------------|-------|
| /wheel | ⏳ Pending | Hooks available | useWheelCycles |
| /spx-wheel | ⏳ Pending | Hooks available | useSPXStatus, useSPXPerformance |

---

## Available SWR Hooks (useMarketData.ts)

### Core Data Hooks
- `useMarketCommentary()` - Live market commentary
- `useDailyTradingPlan()` - Daily trading plan
- `useGammaExpiration(symbol)` - 0DTE gamma expiration data

### GEX & Gamma Hooks
- `useGEX(symbol)` - GEX data
- `useGEXLevels(symbol)` - GEX levels
- `useGEXHistory(symbol, days)` - Historical GEX
- `useGammaIntelligence(symbol, vix)` - Gamma intelligence

### VIX Hooks
- `useVIX()` - Current VIX data
- `useVIXHedgeSignal()` - VIX hedge signals
- `useVIXSignalHistory()` - VIX signal history

### Bot Hooks
- `useARESStatus()`, `useARESPerformance()`, `useARESEquityCurve()`, `useARESPositions()`, `useARESMarketData()`, `useARESTradierStatus()`, `useARESConfig()`
- `useATHENAStatus()`, `useATHENAPositions()`, `useATHENASignals()`, `useATHENAPerformance()`, `useATHENAOracleAdvice()`, `useATHENAMLSignal()`, `useATHENALogs()`
- `useTraderStatus()`, `useTraderPerformance()`, `useTraderPositions()`

### Prophet & ML Hooks
- `useProphetStatus()`, `useOracleLogs()`, `useOraclePredictions()`
- `useMLStatus()`, `useMLFeatureImportance()`, `useMLDataQuality()`, `useMLStrategy()`

### System Hooks
- `useDatabaseStats()`, `useTableFreshness()`, `useSystemHealth()`, `useSystemLogs()`
- `useLogsSummary()`, `useMLLogs()`, `useAutonomousLogs()`
- `useAlerts()`, `useAlertHistory()`
- `useWheelCycles()`, `useSPXStatus()`, `useSPXPerformance()`

---

## End-to-End Testing Checklist

### Manual Testing
1. [x] Open Dashboard - verify all components load
2. [ ] Navigate to GEX page - verify data loads
3. [ ] Return to Dashboard - verify instant load (< 500ms)
4. [ ] Open VIX page - verify data loads
5. [ ] Return to Dashboard - verify instant load
6. [ ] Repeat for all migrated pages

### Automated Testing
Run: `npx playwright test swr-caching.spec.ts`

| Test | Description | Status |
|------|-------------|--------|
| Dashboard loads and caches | Initial data load and cache | ✅ Available |
| Data persists on navigation | Cache survives page changes | ✅ Available |
| MarketCommentary uses cache | SWR indicator visible | ✅ Available |
| Manual refresh works | Refresh button triggers revalidation | ✅ Available |
| Symbol switching maintains cache | Different symbols cached separately | ✅ Available |
| Second load faster than first | Performance improvement | ✅ Available |
| Error state handling | Graceful degradation | ✅ Available |
| Retry button works | Recovery from errors | ✅ Available |

---

## Build & Deploy Checklist
- [x] Run `npm run build` - verify no TypeScript errors
- [ ] Run `npm run lint` - verify no linting errors
- [ ] Run E2E tests - verify all pass
- [x] Create git commit with descriptive message
- [x] Push to branch `claude/fix-dashboard-loading-zWsaJ`
- [ ] Create PR for review

---

## Performance Expectations

| Metric | Before SWR | After SWR |
|--------|------------|-----------|
| Initial page load | 2-5 seconds | 2-5 seconds (unchanged) |
| Return navigation | 2-5 seconds | < 500ms (instant) |
| Background refresh | Manual only | Automatic every 30s-5min |
| Cache persistence | None | SWR in-memory cache |

---

## Migration Summary

### Completed Migrations (7 pages)
1. **Dashboard components** - MarketCommentary, DailyTradingPlan, GammaExpirationWidget
2. **/vix** - VIX dashboard with hedge signals
3. **/ares** - ARES Iron Condor bot
4. **/solomon** - SOLOMON directional spread bot
5. **/prophet** - Prophet AI predictions
6. **/logs** - Master logs dashboard
7. **/gamma** - VIX data via SWR (gamma intelligence uses WebSocket)

### Hooks Infrastructure
- 50+ SWR hooks created and available
- All hooks use consistent configuration with:
  - `keepPreviousData: true` for seamless UX
  - `dedupingInterval: 60000` to prevent redundant requests
  - `errorRetryCount: 3` with 5-second intervals
  - Custom refresh intervals based on data freshness needs

### Remaining Pages
The following pages can be migrated by importing the appropriate hooks from `@/lib/hooks/useMarketData`:
- /database, /alerts, /ml, /scanner, /trader, /wheel, /spx-wheel, /gex

---

*Last Updated: 2025-12-19*
