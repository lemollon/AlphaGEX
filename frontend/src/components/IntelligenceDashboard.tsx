'use client'

import { useState } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Activity,
  BarChart3,
  Clock,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Zap,
  Target,
  AlertTriangle,
  DollarSign,
  ArrowUpRight,
  ArrowDownRight,
  Gauge,
  Timer,
  Layers,
  Calendar,
  Thermometer,
  MapPin,
  AlertCircle
} from 'lucide-react'
import { useIntelligenceFeed, useDailyTradingPlan, useMarketCommentary } from '@/lib/hooks/useMarketData'

// Helper to format timestamps
function formatTimestamp(dateStr: string | null) {
  if (!dateStr) return 'N/A'
  const date = new Date(dateStr)
  return date.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    timeZone: 'America/Chicago'
  }) + ' CT'
}

// Helper for relative time
function getRelativeTime(dateStr: string | null) {
  if (!dateStr) return ''
  const now = new Date()
  const date = new Date(dateStr)
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'just now'
  if (diffMins === 1) return '1 min ago'
  if (diffMins < 60) return `${diffMins} mins ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours === 1) return '1 hour ago'
  return `${diffHours} hours ago`
}

// Sentiment badge component
function SentimentBadge({ sentiment }: { sentiment: string }) {
  const config: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
    BULLISH: { bg: 'bg-success/20', text: 'text-success', icon: <TrendingUp className="w-3 h-3" /> },
    BEARISH: { bg: 'bg-danger/20', text: 'text-danger', icon: <TrendingDown className="w-3 h-3" /> },
    NEUTRAL: { bg: 'bg-text-muted/20', text: 'text-text-muted', icon: <Minus className="w-3 h-3" /> },
  }
  const { bg, text, icon } = config[sentiment] || config.NEUTRAL

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${bg} ${text}`}>
      {icon}
      {sentiment}
    </span>
  )
}

// Expandable card wrapper
function IntelCard({
  title,
  icon: Icon,
  color,
  refreshInterval,
  updatedAt,
  expanded,
  onToggle,
  badge,
  children,
  summary
}: {
  title: string
  icon: React.ElementType
  color: string
  refreshInterval: string
  updatedAt: string | null
  expanded: boolean
  onToggle: () => void
  badge?: React.ReactNode
  children: React.ReactNode
  summary?: React.ReactNode
}) {
  const colorClasses: Record<string, { border: string; bg: string; text: string; hover: string }> = {
    success: { border: 'border-success/30', bg: 'from-success/5', text: 'text-success', hover: 'hover:bg-success/10' },
    primary: { border: 'border-primary/30', bg: 'from-primary/5', text: 'text-primary', hover: 'hover:bg-primary/10' },
    warning: { border: 'border-warning/30', bg: 'from-warning/5', text: 'text-warning', hover: 'hover:bg-warning/10' },
    danger: { border: 'border-danger/30', bg: 'from-danger/5', text: 'text-danger', hover: 'hover:bg-danger/10' },
    info: { border: 'border-info/30', bg: 'from-info/5', text: 'text-info', hover: 'hover:bg-info/10' },
  }
  const colors = colorClasses[color] || colorClasses.primary

  return (
    <div className={`card bg-gradient-to-r ${colors.bg} to-transparent border ${colors.border} transition-all duration-200`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${colors.bg.replace('from-', 'bg-').replace('/5', '/10')}`}>
            <Icon className={`w-4 h-4 ${colors.text}`} />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <Clock className="w-3 h-3" />
              <span>{getRelativeTime(updatedAt)}</span>
              <span className="opacity-50">|</span>
              <span>Updates {refreshInterval}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {badge}
          {!expanded && summary}
          <div className={`p-1.5 rounded-lg ${colors.hover} transition-colors`}>
            {expanded ? (
              <ChevronUp className={`w-4 h-4 ${colors.text}`} />
            ) : (
              <ChevronDown className={`w-4 h-4 ${colors.text}`} />
            )}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {children}
        </div>
      )}
    </div>
  )
}

// Main Dashboard Component
export default function IntelligenceDashboard() {
  const { data: feedData, isLoading: feedLoading, mutate: refreshFeed } = useIntelligenceFeed()
  const { data: planData, isLoading: planLoading, mutate: refreshPlan } = useDailyTradingPlan()
  const { data: commentaryData, isLoading: commentaryLoading, mutate: refreshCommentary } = useMarketCommentary()

  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['bias', 'snapshot', 'commentary'])
  )

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev)
      next.has(section) ? next.delete(section) : next.add(section)
      return next
    })
  }

  const feed = feedData?.data
  const plan = planData?.data
  const commentary = commentaryData?.data

  const refreshAll = () => {
    refreshFeed()
    refreshPlan()
    refreshCommentary()
  }

  if (feedLoading && !feed) {
    return (
      <div className="space-y-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="card animate-pulse">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-background-hover rounded-lg" />
              <div className="space-y-2">
                <div className="h-4 w-32 bg-background-hover rounded" />
                <div className="h-3 w-24 bg-background-hover rounded" />
              </div>
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Market Intelligence</h2>
          <p className="text-xs text-text-muted">Real-time GEX analysis & trading signals</p>
        </div>
        <button
          onClick={refreshAll}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-primary bg-primary/10 rounded-lg hover:bg-primary/20 transition-colors"
        >
          <RefreshCw className="w-3 h-3" />
          Refresh All
        </button>
      </div>

      {/* Market Bias - Hero Card */}
      {feed?.market_bias && (
        <IntelCard
          title="Market Bias"
          icon={Gauge}
          color={feed.market_bias.direction === 'BULLISH' ? 'success' : feed.market_bias.direction === 'BEARISH' ? 'danger' : 'primary'}
          refreshInterval="every 2 min"
          updatedAt={feed.market_bias.updated_at}
          expanded={expandedSections.has('bias')}
          onToggle={() => toggleSection('bias')}
          badge={<SentimentBadge sentiment={feed.market_bias.direction} />}
        >
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-3 bg-success/10 rounded-lg">
              <div className="text-2xl font-bold text-success">{feed.market_bias.bullish_signals}</div>
              <div className="text-xs text-text-muted">Bullish Signals</div>
            </div>
            <div className="text-center p-3 bg-text-muted/10 rounded-lg">
              <div className="text-2xl font-bold text-text-primary">{Math.round(feed.market_bias.confidence)}%</div>
              <div className="text-xs text-text-muted">Confidence</div>
            </div>
            <div className="text-center p-3 bg-danger/10 rounded-lg">
              <div className="text-2xl font-bold text-danger">{feed.market_bias.bearish_signals}</div>
              <div className="text-xs text-text-muted">Bearish Signals</div>
            </div>
          </div>
        </IntelCard>
      )}

      {/* Live Market Snapshot */}
      {feed?.market_snapshot && (
        <IntelCard
          title="Live Market Data"
          icon={Activity}
          color="primary"
          refreshInterval="every 2 min"
          updatedAt={feed.market_snapshot.updated_at}
          expanded={expandedSections.has('snapshot')}
          onToggle={() => toggleSection('snapshot')}
          summary={
            <span className="text-sm font-semibold text-text-primary">
              SPY ${feed.market_snapshot.spy_price?.toFixed(2)}
            </span>
          }
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">SPY Price</div>
                <div className="text-lg font-bold text-text-primary">${feed.market_snapshot.spy_price?.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">VIX</div>
                <div className="text-lg font-bold text-warning">{feed.market_snapshot.vix?.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">Net GEX</div>
                <div className={`text-lg font-bold ${feed.market_snapshot.net_gex_billions >= 0 ? 'text-success' : 'text-danger'}`}>
                  ${feed.market_snapshot.net_gex_billions}B
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">Regime</div>
                <div className="text-sm font-medium text-text-primary">{feed.market_snapshot.regime?.replace(/_/g, ' ')}</div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-2 border border-primary/20 rounded-lg">
                <div className="text-xs text-text-muted">Call Wall</div>
                <div className="text-sm font-semibold text-primary">${feed.market_snapshot.call_wall?.toFixed(0)}</div>
                <div className="text-xs text-text-muted">{feed.market_snapshot.dist_to_call_pct?.toFixed(1)}% away</div>
              </div>
              <div className="p-2 border border-warning/20 rounded-lg">
                <div className="text-xs text-text-muted">Flip Point</div>
                <div className="text-sm font-semibold text-warning">${feed.market_snapshot.flip_point?.toFixed(0)}</div>
                <div className={`text-xs ${feed.market_snapshot.above_flip ? 'text-success' : 'text-danger'}`}>
                  {feed.market_snapshot.above_flip ? 'ABOVE' : 'BELOW'}
                </div>
              </div>
              <div className="p-2 border border-info/20 rounded-lg">
                <div className="text-xs text-text-muted">Put Wall</div>
                <div className="text-sm font-semibold text-info">${feed.market_snapshot.put_wall?.toFixed(0)}</div>
                <div className="text-xs text-text-muted">{feed.market_snapshot.dist_to_put_pct?.toFixed(1)}% away</div>
              </div>
            </div>

            {feed.market_snapshot.psychology_trap && (
              <div className="flex items-center gap-2 p-2 bg-danger/10 border border-danger/20 rounded-lg">
                <AlertTriangle className="w-4 h-4 text-danger" />
                <span className="text-sm text-danger font-medium">
                  Psychology Trap: {feed.market_snapshot.psychology_trap}
                </span>
              </div>
            )}
          </div>
        </IntelCard>
      )}

      {/* AI Commentary */}
      {commentary && (
        <IntelCard
          title="AI Market Commentary"
          icon={Zap}
          color="info"
          refreshInterval="every 2 min"
          updatedAt={commentary.generated_at}
          expanded={expandedSections.has('commentary')}
          onToggle={() => toggleSection('commentary')}
        >
          <div className="prose prose-sm max-w-none">
            <p className="text-text-primary leading-relaxed whitespace-pre-wrap text-sm">
              {commentary.commentary || 'Loading commentary...'}
            </p>
          </div>
        </IntelCard>
      )}

      {/* Options Flow */}
      {feed?.options_flow && (
        <IntelCard
          title="Smart Money Flow"
          icon={DollarSign}
          color={feed.options_flow.sentiment === 'BULLISH' ? 'success' : feed.options_flow.sentiment === 'BEARISH' ? 'danger' : 'primary'}
          refreshInterval="every 5 min"
          updatedAt={feed.options_flow.updated_at}
          expanded={expandedSections.has('flow')}
          onToggle={() => toggleSection('flow')}
          badge={<SentimentBadge sentiment={feed.options_flow.sentiment} />}
          summary={
            <span className="text-xs text-text-muted">
              P/C: {feed.options_flow.put_call_ratio?.toFixed(2)}
            </span>
          }
        >
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">Put/Call Ratio</div>
                <div className={`text-xl font-bold ${feed.options_flow.put_call_ratio > 1.2 ? 'text-danger' : feed.options_flow.put_call_ratio < 0.8 ? 'text-success' : 'text-text-primary'}`}>
                  {feed.options_flow.put_call_ratio?.toFixed(2)}
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">Unusual Calls</div>
                <div className="text-xl font-bold text-success">
                  {feed.options_flow.unusual_call_volume?.toLocaleString()}
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">Unusual Puts</div>
                <div className="text-xl font-bold text-danger">
                  {feed.options_flow.unusual_put_volume?.toLocaleString()}
                </div>
              </div>
            </div>
            {feed.options_flow.smart_money_signal && (
              <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg">
                <div className="text-sm text-text-primary">
                  <strong>Signal:</strong> {feed.options_flow.smart_money_signal}
                </div>
              </div>
            )}
          </div>
        </IntelCard>
      )}

      {/* GEX History */}
      {feed?.gex_history && (
        <IntelCard
          title="GEX Momentum"
          icon={BarChart3}
          color={feed.gex_history.gex_trend?.includes('RISING') ? 'success' : feed.gex_history.gex_trend?.includes('FALLING') ? 'danger' : 'primary'}
          refreshInterval="every 5 min"
          updatedAt={feed.gex_history.updated_at}
          expanded={expandedSections.has('history')}
          onToggle={() => toggleSection('history')}
          summary={
            <div className="flex items-center gap-1">
              {feed.gex_history.gex_change_billions >= 0 ? (
                <ArrowUpRight className="w-4 h-4 text-success" />
              ) : (
                <ArrowDownRight className="w-4 h-4 text-danger" />
              )}
              <span className={`text-xs font-medium ${feed.gex_history.gex_change_billions >= 0 ? 'text-success' : 'text-danger'}`}>
                {feed.gex_history.gex_change_billions >= 0 ? '+' : ''}{feed.gex_history.gex_change_billions}B
              </span>
            </div>
          }
        >
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">Yesterday</div>
                <div className="text-lg font-bold text-text-secondary">
                  ${feed.gex_history.yesterday_gex_billions}B
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">Today</div>
                <div className={`text-lg font-bold ${feed.gex_history.today_gex_billions >= 0 ? 'text-success' : 'text-danger'}`}>
                  ${feed.gex_history.today_gex_billions}B
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">Change</div>
                <div className={`text-lg font-bold ${feed.gex_history.gex_change_billions >= 0 ? 'text-success' : 'text-danger'}`}>
                  {feed.gex_history.gex_change_billions >= 0 ? '+' : ''}{feed.gex_history.gex_change_billions}B
                </div>
              </div>
            </div>
            <div className="flex items-center justify-between p-2 bg-background-hover rounded-lg">
              <span className="text-xs text-text-muted">Trend</span>
              <span className={`text-sm font-medium ${feed.gex_history.gex_trend?.includes('RISING') ? 'text-success' : feed.gex_history.gex_trend?.includes('FALLING') ? 'text-danger' : 'text-text-primary'}`}>
                {feed.gex_history.gex_trend?.replace(/_/g, ' ')}
              </span>
            </div>
          </div>
        </IntelCard>
      )}

      {/* Intraday Momentum */}
      {feed?.intraday_momentum && (
        <IntelCard
          title="Intraday Momentum"
          icon={Activity}
          color={feed.intraday_momentum.direction === 'BULLISH' ? 'success' : feed.intraday_momentum.direction === 'BEARISH' ? 'danger' : 'primary'}
          refreshInterval="every 5 min"
          updatedAt={feed.intraday_momentum.updated_at}
          expanded={expandedSections.has('intraday')}
          onToggle={() => toggleSection('intraday')}
          badge={<SentimentBadge sentiment={feed.intraday_momentum.direction} />}
        >
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">1 Hour Ago</div>
                <div className="text-lg font-bold text-text-secondary">
                  ${feed.intraday_momentum.gex_1h_ago_billions}B
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">Now</div>
                <div className={`text-lg font-bold ${feed.intraday_momentum.gex_current_billions >= 0 ? 'text-success' : 'text-danger'}`}>
                  ${feed.intraday_momentum.gex_current_billions}B
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="p-2 bg-background-hover rounded-lg flex items-center justify-between">
                <span className="text-xs text-text-muted">Momentum</span>
                <span className="text-sm font-medium text-text-primary">{feed.intraday_momentum.momentum}</span>
              </div>
              <div className="p-2 bg-background-hover rounded-lg flex items-center justify-between">
                <span className="text-xs text-text-muted">Speed</span>
                <span className={`text-sm font-medium ${feed.intraday_momentum.speed === 'FAST' ? 'text-warning' : 'text-text-primary'}`}>
                  {feed.intraday_momentum.speed}
                </span>
              </div>
            </div>
          </div>
        </IntelCard>
      )}

      {/* Pattern Performance */}
      {feed?.pattern_performance && feed.pattern_performance.patterns?.length > 0 && (
        <IntelCard
          title="Pattern Performance"
          icon={Target}
          color="success"
          refreshInterval="every 30 min"
          updatedAt={feed.pattern_performance.updated_at}
          expanded={expandedSections.has('patterns')}
          onToggle={() => toggleSection('patterns')}
          summary={
            feed.pattern_performance.best_pattern && (
              <span className="text-xs text-success">
                Best: {feed.pattern_performance.best_pattern.win_rate}% WR
              </span>
            )
          }
        >
          <div className="space-y-2">
            <div className="text-xs text-text-muted mb-2">
              Current Regime: <span className="text-text-primary font-medium">{feed.pattern_performance.current_regime?.replace(/_/g, ' ')}</span>
            </div>
            {feed.pattern_performance.patterns.map((pattern: any, idx: number) => (
              <div key={idx} className="flex items-center justify-between p-2 bg-background-hover rounded-lg">
                <span className="text-sm text-text-primary">{pattern.pattern || 'Unknown'}</span>
                <div className="flex items-center gap-3">
                  <span className={`text-sm font-medium ${pattern.win_rate >= 60 ? 'text-success' : pattern.win_rate >= 40 ? 'text-warning' : 'text-danger'}`}>
                    {pattern.win_rate}% WR
                  </span>
                  <span className={`text-sm ${pattern.avg_pnl >= 0 ? 'text-success' : 'text-danger'}`}>
                    ${pattern.avg_pnl?.toFixed(0)} avg
                  </span>
                </div>
              </div>
            ))}
          </div>
        </IntelCard>
      )}

      {/* Trading Windows */}
      {feed?.trading_windows && (
        <IntelCard
          title="Trading Windows"
          icon={Timer}
          color={feed.trading_windows.avoid_trading ? 'danger' : feed.trading_windows.market_status === 'OPEN' ? 'success' : 'primary'}
          refreshInterval="every 1 min"
          updatedAt={feed.trading_windows.updated_at}
          expanded={expandedSections.has('windows')}
          onToggle={() => toggleSection('windows')}
          badge={
            <span className={`text-xs font-medium px-2 py-0.5 rounded ${feed.trading_windows.market_status === 'OPEN' ? 'bg-success/20 text-success' : 'bg-text-muted/20 text-text-muted'}`}>
              {feed.trading_windows.market_status}
            </span>
          }
          summary={
            <span className="text-xs text-text-muted">
              {feed.trading_windows.current_window?.replace(/_/g, ' ')}
            </span>
          }
        >
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">Current Window</div>
                <div className="text-sm font-bold text-text-primary">
                  {feed.trading_windows.current_window?.replace(/_/g, ' ') || 'N/A'}
                </div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg">
                <div className="text-xs text-text-muted mb-1">Next Window</div>
                <div className="text-sm font-medium text-text-secondary">
                  {feed.trading_windows.next_window?.replace(/_/g, ' ') || 'N/A'}
                  {feed.trading_windows.minutes_until_next > 0 && (
                    <span className="text-xs text-text-muted ml-1">
                      ({feed.trading_windows.minutes_until_next}m)
                    </span>
                  )}
                </div>
              </div>
            </div>
            {feed.trading_windows.recommendation && (
              <div className={`p-3 rounded-lg ${feed.trading_windows.avoid_trading ? 'bg-danger/10 border border-danger/20' : 'bg-primary/10 border border-primary/20'}`}>
                <div className="flex items-start gap-2">
                  {feed.trading_windows.avoid_trading ? (
                    <AlertTriangle className="w-4 h-4 text-danger flex-shrink-0 mt-0.5" />
                  ) : (
                    <Zap className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
                  )}
                  <span className={`text-sm ${feed.trading_windows.avoid_trading ? 'text-danger' : 'text-text-primary'}`}>
                    {feed.trading_windows.recommendation}
                  </span>
                </div>
              </div>
            )}
          </div>
        </IntelCard>
      )}

      {/* VIX Term Structure */}
      {feed?.vix_term_structure && (
        <IntelCard
          title="VIX Term Structure"
          icon={Thermometer}
          color={feed.vix_term_structure.signal === 'BULLISH' ? 'success' : feed.vix_term_structure.signal === 'BEARISH' ? 'danger' : 'primary'}
          refreshInterval="every 5 min"
          updatedAt={feed.vix_term_structure.updated_at}
          expanded={expandedSections.has('vix')}
          onToggle={() => toggleSection('vix')}
          badge={<SentimentBadge sentiment={feed.vix_term_structure.signal === 'NEUTRAL_BULLISH' ? 'BULLISH' : feed.vix_term_structure.signal} />}
          summary={
            <span className="text-xs text-text-muted">
              {feed.vix_term_structure.term_structure?.replace(/_/g, ' ')}
            </span>
          }
        >
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">VIX Spot</div>
                <div className="text-lg font-bold text-warning">{feed.vix_term_structure.vix_spot?.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">VIX 1M</div>
                <div className="text-lg font-bold text-text-primary">{feed.vix_term_structure.vix_1m?.toFixed(2)}</div>
              </div>
              <div className="p-3 bg-background-hover rounded-lg text-center">
                <div className="text-xs text-text-muted mb-1">Contango</div>
                <div className={`text-lg font-bold ${feed.vix_term_structure.contango_pct >= 0 ? 'text-success' : 'text-danger'}`}>
                  {feed.vix_term_structure.contango_pct >= 0 ? '+' : ''}{feed.vix_term_structure.contango_pct}%
                </div>
              </div>
            </div>
            {feed.vix_term_structure.interpretation && (
              <div className="p-2 bg-background-hover rounded-lg">
                <span className="text-sm text-text-secondary">{feed.vix_term_structure.interpretation}</span>
              </div>
            )}
          </div>
        </IntelCard>
      )}

      {/* Strike Clustering */}
      {feed?.strike_clustering && (
        <IntelCard
          title="Strike Clustering"
          icon={Layers}
          color={feed.strike_clustering.institutional_bias === 'BULLISH' ? 'success' : feed.strike_clustering.institutional_bias === 'BEARISH' ? 'danger' : 'primary'}
          refreshInterval="every 5 min"
          updatedAt={feed.strike_clustering.updated_at}
          expanded={expandedSections.has('strikes')}
          onToggle={() => toggleSection('strikes')}
          badge={<SentimentBadge sentiment={feed.strike_clustering.institutional_bias} />}
        >
          <div className="space-y-3">
            {feed.strike_clustering.magnetic_levels?.length > 0 && (
              <div>
                <div className="text-xs text-text-muted mb-2">Magnetic Price Levels (High OI)</div>
                <div className="flex flex-wrap gap-2">
                  {feed.strike_clustering.magnetic_levels.map((level: number, idx: number) => (
                    <span key={idx} className="px-3 py-1 bg-primary/10 border border-primary/20 rounded-full text-sm font-medium text-primary">
                      ${level?.toFixed(0)}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {feed.strike_clustering.interpretation && (
              <div className="p-2 bg-background-hover rounded-lg">
                <span className="text-sm text-text-secondary">{feed.strike_clustering.interpretation}</span>
              </div>
            )}
          </div>
        </IntelCard>
      )}

      {/* Key Events */}
      {feed?.key_events && (feed.key_events.high_impact_today || feed.key_events.fed_day || feed.key_events.triple_witching) && (
        <IntelCard
          title="Key Events"
          icon={Calendar}
          color="warning"
          refreshInterval="every 30 min"
          updatedAt={feed.key_events.updated_at}
          expanded={expandedSections.has('events')}
          onToggle={() => toggleSection('events')}
          badge={
            feed.key_events.fed_day ? (
              <span className="text-xs font-medium px-2 py-0.5 rounded bg-danger/20 text-danger">FED DAY</span>
            ) : feed.key_events.high_impact_today ? (
              <span className="text-xs font-medium px-2 py-0.5 rounded bg-warning/20 text-warning">HIGH IMPACT</span>
            ) : null
          }
        >
          <div className="space-y-2">
            {feed.key_events.fed_day && (
              <div className="flex items-center gap-2 p-2 bg-danger/10 border border-danger/20 rounded-lg">
                <AlertCircle className="w-4 h-4 text-danger" />
                <span className="text-sm text-danger font-medium">FOMC / Fed Event Today</span>
              </div>
            )}
            {feed.key_events.triple_witching && (
              <div className="flex items-center gap-2 p-2 bg-warning/10 border border-warning/20 rounded-lg">
                <AlertTriangle className="w-4 h-4 text-warning" />
                <span className="text-sm text-warning font-medium">Monthly Options Expiration</span>
              </div>
            )}
            {feed.key_events.interpretation && (
              <div className="p-2 bg-background-hover rounded-lg">
                <span className="text-sm text-text-secondary">{feed.key_events.interpretation}</span>
              </div>
            )}
          </div>
        </IntelCard>
      )}

      {/* Daily Trading Plan */}
      {plan && (
        <IntelCard
          title="Daily Trading Plan"
          icon={Target}
          color="warning"
          refreshInterval="every 5 min"
          updatedAt={plan.generated_at}
          expanded={expandedSections.has('plan')}
          onToggle={() => toggleSection('plan')}
        >
          <div className="prose prose-sm max-w-none max-h-96 overflow-y-auto pr-2">
            <div className="text-text-primary whitespace-pre-wrap leading-relaxed text-sm">
              {plan.plan || 'Loading trading plan...'}
            </div>
          </div>
        </IntelCard>
      )}

      {/* Footer */}
      <div className="text-center text-xs text-text-muted pt-2">
        <span>Data refreshes automatically</span>
        <span className="mx-2">|</span>
        <span>Last sync: {formatTimestamp(feed?.generated_at)}</span>
      </div>
    </div>
  )
}
