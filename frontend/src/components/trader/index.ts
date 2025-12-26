// Trader Components - Unified export for all trading UI components

// Core Portfolio Components
export { default as LivePortfolio } from './LivePortfolio'
export { default as OpenPositionsLive } from './OpenPositionsLive'
export { default as AllOpenPositions } from './AllOpenPositions'
export { default as LiveEquityCurve } from './LiveEquityCurve'

// Trade Story & Decisions
export { default as TradeStoryCard } from './TradeStoryCard'
export type { TradeDecision } from './TradeStoryCard'

// Transparency & Reasoning - NEW
export { default as LastScanSummary } from './LastScanSummary'
export { default as SignalConflictTracker } from './SignalConflictTracker'
export { default as PositionEntryContext } from './PositionEntryContext'

// Status & Information
export { default as BotStatusBanner } from './BotStatusBanner'
export { default as TodayReportCard } from './TodayReportCard'
export { default as WhyNotTrading } from './WhyNotTrading'
export { default as RiskMetrics } from './RiskMetrics'
export { default as PerformanceComparison } from './PerformanceComparison'

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
export { default as EquityCurve } from './EquityCurve'
export { default as DecisionLogViewer } from './DecisionLogViewer'
export { default as MLModelStatus } from './MLModelStatus'
export { default as PerformanceCards } from './PerformanceCards'
export { default as ExportButtons } from './ExportButtons'
export { default as WheelDashboard } from './WheelDashboard'

// Re-export types from LivePortfolio
export type { LivePnLData, LivePosition, EquityDataPoint, TimePeriod } from './LivePortfolio'

// Re-export types from LiveEquityCurve (with alias to avoid conflict)
export type { EquityPoint } from './LiveEquityCurve'
