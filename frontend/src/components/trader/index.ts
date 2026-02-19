// Trader Components - Unified export for all trading UI components

// Unified Branding System - NEW
export {
  BOT_BRANDS,
  UNIFIED_TABS,
  DataFreshnessIndicator,
  BotCard,
  EmptyState,
  LoadingState,
  StatCard,
  StatusBadge,
  DirectionIndicator,
  PnLDisplay,
  BotPageHeader,
  // NEW: Time & Context Display Components
  formatDuration,
  TimeInPosition,
  DateRangeDisplay,
  BreakevenDistance,
  EntryContext,
  UnlockConditions,
  DrawdownDisplay,
} from './BotBranding'
export type { BotName, BotBrand, TabId } from './BotBranding'

// Core Portfolio Components
// NOTE: LivePortfolio, LiveEquityCurve, EquityCurve, PresetPerformanceChart
// are NOT re-exported here to avoid pulling recharts into every page that
// imports from this barrel. Import them directly if needed:
//   import LivePortfolio from '@/components/trader/LivePortfolio'
export { default as OpenPositionsLive } from './OpenPositionsLive'
export { default as AllOpenPositions } from './AllOpenPositions'

// Trade Story & Decisions
export { default as TradeStoryCard } from './TradeStoryCard'
export type { TradeDecision } from './TradeStoryCard'

// Transparency & Reasoning - NEW
export { default as LastScanSummary } from './LastScanSummary'
export { default as SignalConflictTracker } from './SignalConflictTracker'
export { default as PositionEntryContext } from './PositionEntryContext'

// Enhanced Scan Activity - MAXIMUM TRANSPARENCY
export { default as ScanDetailCard } from './ScanDetailCard'
export type { ScanData, ScanCheck, SignalData, MarketContext, ScanTimestamps, TradeDetails } from './ScanDetailCard'

// Status & Information
export { default as BotStatusBanner } from './BotStatusBanner'
export { default as TodayReportCard } from './TodayReportCard'
export { default as WhyNotTrading } from './WhyNotTrading'
export { default as RiskMetrics } from './RiskMetrics'
export { default as PerformanceComparison } from './PerformanceComparison'
// PresetPerformanceChart removed from barrel - import directly to avoid recharts in bundle
export { default as UnrealizedPnLCard } from './UnrealizedPnLCard'
export { default as HedgeSignalCard } from './HedgeSignalCard'

// Activity & Timeline
export { default as ActivityTimeline } from './ActivityTimeline'

// Notifications
export { default as ExitNotification, ExitNotificationContainer } from './ExitNotification'

// Actions & Controls
export { default as QuickActions } from './QuickActions'

// Filters & Search
export { default as DecisionFilter } from './DecisionFilter'
export type { DecisionFilters } from './DecisionFilter'

// Modals
export { default as PositionDetailModal } from './PositionDetailModal'

// Legacy / Existing Components
// EquityCurve removed from barrel - import directly to avoid recharts in bundle
export { default as DecisionLogViewer } from './DecisionLogViewer'
export { default as MLModelStatus } from './MLModelStatus'
export { default as PerformanceCards } from './PerformanceCards'
export { default as ExportButtons } from './ExportButtons'
export { default as WheelDashboard } from './WheelDashboard'

// Types re-exported separately (type-only imports don't pull in runtime code)
export type { LivePnLData, LivePosition, EquityDataPoint, TimePeriod } from './LivePortfolio'
export type { EquityPoint } from './LiveEquityCurve'

// Unified Bot Metrics - Single Source of Truth for all bot statistics
// Use this instead of calculating stats in frontend components
export { default as UnifiedBotMetrics, StatCard as UnifiedStatCard, CapitalSourceBadge, ReconciliationStatus } from './UnifiedBotMetrics'

// Capital Configuration Panel - For setting starting capital and resetting bot data
// Use in Config tabs of bot pages
export { default as CapitalConfigPanel } from './CapitalConfigPanel'
