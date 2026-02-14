'use client'

import { useState, useMemo, useCallback, memo } from 'react'
import Link from 'next/link'
import {
  Bot,
  Activity,
  TrendingUp,
  TrendingDown,
  Pause,
  Play,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Shield,
  Sword,
  Target,
  Zap,
  Flame,
  Rocket,
  Boxes
} from 'lucide-react'
import {
  useFortressStatus,
  useSolomonStatus,
  useANCHORStatus,
  useGideonStatus,
  useSamsonStatus,
  useJUBILEEStatus,
  useFortressLivePnL,
  useSolomonLivePnL,
  useANCHORLivePnL,
  useGideonLivePnL,
  useSamsonLivePnL,
  useJUBILEELivePnL,
  useAGAPEStatus,
  useAGAPEBTCStatus,
  useAGAPEXRPStatus,
} from '@/lib/hooks/useMarketData'

// PERFORMANCE FIX: Move colorClasses outside component (was recreated every render)
const COLOR_CLASSES: Record<string, { bg: string; border: string; text: string }> = {
  blue: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-500' },
  purple: { bg: 'bg-purple-500/10', border: 'border-purple-500/30', text: 'text-purple-500' },
  amber: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-500' },
  cyan: { bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', text: 'text-cyan-500' },
  rose: { bg: 'bg-rose-500/10', border: 'border-rose-500/30', text: 'text-rose-500' },
  orange: { bg: 'bg-orange-500/10', border: 'border-orange-500/30', text: 'text-orange-500' },
}

// Helper to format timestamp in Central Time
function formatCentralTime(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', {
      timeZone: 'America/Chicago',
      hour: '2-digit',
      minute: '2-digit',
      hour12: true
    }) + ' CT'
  } catch {
    return ''
  }
}

interface BotStatusCardProps {
  name: string
  icon: React.ReactNode
  href: string
  status: any
  livePnL: any
  color: string
  isLoading: boolean
}

// PERFORMANCE FIX: Wrap BotStatusCard with React.memo to prevent unnecessary re-renders
const BotStatusCard = memo(function BotStatusCard({ name, icon, href, status, livePnL, color, isLoading }: BotStatusCardProps) {
  const isActive = status?.is_active || status?.bot_status === 'ACTIVE' || status?.status === 'active'
  // API returns 'open_positions' as a count, not 'open_positions_count'
  const openPositionsCount = status?.open_positions || status?.open_positions_count || status?.positions?.open?.length || 0
  const hasOpenPositions = openPositionsCount > 0

  // Get P&L values - handle both response formats
  // IMPORTANT: Do NOT fall back to total_pnl for unrealized - that's realized P&L!
  // When no open positions exist, unrealized should be 0, not the total realized P&L
  const totalPnL = livePnL?.total_unrealized_pnl ?? livePnL?.unrealized_pnl ?? status?.unrealized_pnl ?? 0
  const todayPnL = livePnL?.today_pnl || status?.today_pnl || 0

  // PERFORMANCE FIX: Use moved constant instead of creating new object every render
  const colors = COLOR_CLASSES[color] || COLOR_CLASSES.blue

  if (isLoading) {
    return (
      <div className={`p-4 rounded-lg border ${colors.border} ${colors.bg} animate-pulse`}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-background-hover rounded-lg" />
          <div className="flex-1">
            <div className="h-4 w-20 bg-background-hover rounded mb-2" />
            <div className="h-3 w-16 bg-background-hover rounded" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <Link href={href}>
      <div className={`p-4 rounded-lg border ${colors.border} ${colors.bg} hover:bg-opacity-20 transition-all cursor-pointer`}>
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${colors.bg}`}>
              {icon}
            </div>
            <div>
              <h4 className="font-bold text-text-primary">{name}</h4>
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-success animate-pulse' : 'bg-text-muted'}`} />
                <span className={`text-xs ${isActive ? 'text-success' : 'text-text-muted'}`}>
                  {isActive ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>
          </div>
          {hasOpenPositions && (
            <span className="px-2 py-1 text-xs font-medium bg-primary/20 text-primary rounded">
              {openPositionsCount} open
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="p-2 bg-background-card/50 rounded">
            <div className="text-xs text-text-muted mb-1">Today P&L</div>
            <div className={`text-sm font-bold ${todayPnL >= 0 ? 'text-success' : 'text-danger'}`}>
              {todayPnL >= 0 ? '+' : ''}{typeof todayPnL === 'number' ? `$${todayPnL.toFixed(2)}` : '$0.00'}
            </div>
          </div>
          <div className="p-2 bg-background-card/50 rounded">
            <div className="text-xs text-text-muted mb-1">Unrealized</div>
            <div className={`text-sm font-bold ${totalPnL >= 0 ? 'text-success' : 'text-danger'}`}>
              {totalPnL >= 0 ? '+' : ''}{typeof totalPnL === 'number' ? `$${totalPnL.toFixed(2)}` : '$0.00'}
            </div>
          </div>
        </div>

        {status?.last_scan_at && (
          <div className="mt-2 text-xs text-text-muted">
            Last scan: {formatCentralTime(status.last_scan_at)}
          </div>
        )}
      </div>
    </Link>
  )
})  // End of React.memo wrapped BotStatusCard

export default function BotStatusOverview() {
  const [expanded, setExpanded] = useState(true)

  // Live trading bots
  const { data: aresStatus, isLoading: aresLoading, mutate: refreshAres } = useFortressStatus()
  const { data: solomonStatus, isLoading: solomonLoading, mutate: refreshAthena } = useSolomonStatus()
  const { data: anchorStatus, isLoading: anchorLoading, mutate: refreshAnchor } = useANCHORStatus()

  // Paper trading bots
  const { data: icarusStatus, isLoading: icarusLoading, mutate: refreshIcarus } = useGideonStatus()
  const { data: titanStatus, isLoading: titanLoading, mutate: refreshTitan } = useSamsonStatus()
  const { data: jubileeStatus, isLoading: jubileeLoading, mutate: refreshJubilee } = useJUBILEEStatus()

  // Crypto futures bots
  const { data: agapeEthStatus, isLoading: agapeEthLoading, mutate: refreshAgapeEth } = useAGAPEStatus()
  const { data: agapeBtcStatus, isLoading: agapeBtcLoading, mutate: refreshAgapeBtc } = useAGAPEBTCStatus()
  const { data: agapeXrpStatus, isLoading: agapeXrpLoading, mutate: refreshAgapeXrp } = useAGAPEXRPStatus()

  const { data: aresLivePnL } = useFortressLivePnL()
  const { data: solomonLivePnL } = useSolomonLivePnL()
  const { data: anchorLivePnL } = useANCHORLivePnL()
  const { data: icarusLivePnL } = useGideonLivePnL()
  const { data: titanLivePnL } = useSamsonLivePnL()
  const { data: jubileeLivePnL } = useJUBILEELivePnL()

  // PERFORMANCE FIX: useCallback for refreshAll to prevent child re-renders
  const refreshAll = useCallback(() => {
    refreshAres()
    refreshAthena()
    refreshAnchor()
    refreshIcarus()
    refreshTitan()
    refreshJubilee()
    refreshAgapeEth()
    refreshAgapeBtc()
    refreshAgapeXrp()
  }, [refreshAres, refreshAthena, refreshAnchor, refreshIcarus, refreshTitan, refreshJubilee, refreshAgapeEth, refreshAgapeBtc, refreshAgapeXrp])

  // PERFORMANCE FIX: useMemo for calculated P&L values (was recalculating every render)
  const { totalTodayPnL, totalUnrealizedPnL, paperTodayPnL } = useMemo(() => ({
    totalTodayPnL: (aresLivePnL?.data?.today_pnl || 0) +
                   (solomonLivePnL?.data?.today_pnl || 0) +
                   (anchorLivePnL?.data?.today_pnl || 0),
    totalUnrealizedPnL: (aresLivePnL?.data?.total_unrealized_pnl || 0) +
                        (solomonLivePnL?.data?.total_unrealized_pnl || 0) +
                        (anchorLivePnL?.data?.total_unrealized_pnl || 0),
    paperTodayPnL: (icarusLivePnL?.data?.today_pnl || 0) +
                   (titanLivePnL?.data?.today_pnl || 0) +
                   (jubileeLivePnL?.net_profit || 0)
  }), [aresLivePnL, solomonLivePnL, anchorLivePnL, icarusLivePnL, titanLivePnL, jubileeLivePnL])

  // PERFORMANCE FIX: useMemo for active bot counts (was filtering on every render)
  const { activeLiveBots, activePaperBots, totalActiveBots } = useMemo(() => {
    const live = [
      aresStatus?.data?.is_active || aresStatus?.data?.bot_status === 'ACTIVE',
      solomonStatus?.data?.is_active || solomonStatus?.data?.bot_status === 'ACTIVE',
      anchorStatus?.data?.is_active || anchorStatus?.data?.status === 'active'
    ].filter(Boolean).length

    const paper = [
      icarusStatus?.data?.is_active || icarusStatus?.data?.bot_status === 'ACTIVE',
      titanStatus?.data?.is_active || titanStatus?.data?.bot_status === 'ACTIVE',
      jubileeStatus?.box_spread?.enabled || jubileeStatus?.ic_trading?.enabled,
    ].filter(Boolean).length

    const crypto = [
      agapeEthStatus?.data?.status === 'ACTIVE',
      agapeBtcStatus?.data?.status === 'ACTIVE',
      agapeXrpStatus?.data?.status === 'ACTIVE',
    ].filter(Boolean).length

    return { activeLiveBots: live, activePaperBots: paper, activeCryptoBots: crypto, totalActiveBots: live + paper + crypto }
  }, [aresStatus, solomonStatus, anchorStatus, icarusStatus, titanStatus, jubileeStatus, agapeEthStatus, agapeBtcStatus, agapeXrpStatus])

  return (
    <div className="card bg-gradient-to-r from-primary/5 to-transparent border border-primary/20">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10">
            <Bot className="w-5 h-5 text-primary" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-text-primary">Trading Bots</h3>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 bg-success rounded-full animate-pulse" />
                {totalActiveBots}/9 active
              </span>
              <span className={totalTodayPnL >= 0 ? 'text-success' : 'text-danger'}>
                Live: {totalTodayPnL >= 0 ? '+' : ''}${totalTodayPnL.toFixed(0)}
              </span>
              {paperTodayPnL !== 0 && (
                <span className={`${paperTodayPnL >= 0 ? 'text-cyan-500' : 'text-danger'}`}>
                  Paper: {paperTodayPnL >= 0 ? '+' : ''}${paperTodayPnL.toFixed(0)}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={(e) => {
              e.stopPropagation()
              refreshAll()
            }}
            className="p-1.5 rounded-lg hover:bg-primary/10 transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-primary" />
          </button>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-primary" />
          ) : (
            <ChevronDown className="w-5 h-5 text-primary" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border/50 animate-fade-in">
          {/* Summary Bar */}
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="p-3 bg-background-hover rounded-lg text-center">
              <div className="text-xs text-text-muted mb-1">Today's P&L</div>
              <div className={`text-xl font-bold ${totalTodayPnL >= 0 ? 'text-success' : 'text-danger'}`}>
                {totalTodayPnL >= 0 ? '+' : ''}${totalTodayPnL.toFixed(2)}
              </div>
            </div>
            <div className="p-3 bg-background-hover rounded-lg text-center">
              <div className="text-xs text-text-muted mb-1">Unrealized P&L</div>
              <div className={`text-xl font-bold ${totalUnrealizedPnL >= 0 ? 'text-success' : 'text-danger'}`}>
                {totalUnrealizedPnL >= 0 ? '+' : ''}${totalUnrealizedPnL.toFixed(2)}
              </div>
            </div>
          </div>

          {/* Live Trading */}
          <div className="mb-3">
            <div className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">Live Trading</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <BotStatusCard
                name="FORTRESS"
                icon={<Sword className="w-5 h-5 text-blue-500" />}
                href="/fortress"
                status={aresStatus?.data}
                livePnL={aresLivePnL?.data}
                color="blue"
                isLoading={aresLoading}
              />
              <BotStatusCard
                name="SOLOMON"
                icon={<Target className="w-5 h-5 text-purple-500" />}
                href="/solomon"
                status={solomonStatus?.data}
                livePnL={solomonLivePnL?.data}
                color="purple"
                isLoading={solomonLoading}
              />
              <BotStatusCard
                name="ANCHOR"
                icon={<Shield className="w-5 h-5 text-amber-500" />}
                href="/anchor"
                status={anchorStatus?.data}
                livePnL={anchorLivePnL?.data}
                color="amber"
                isLoading={anchorLoading}
              />
              <BotStatusCard
                name="GIDEON"
                icon={<Flame className="w-5 h-5 text-cyan-500" />}
                href="/gideon"
                status={icarusStatus?.data}
                livePnL={icarusLivePnL?.data}
                color="cyan"
                isLoading={icarusLoading}
              />
              <BotStatusCard
                name="SAMSON"
                icon={<Rocket className="w-5 h-5 text-rose-500" />}
                href="/samson"
                status={titanStatus?.data}
                livePnL={titanLivePnL?.data}
                color="rose"
                isLoading={titanLoading}
              />
              <BotStatusCard
                name="JUBILEE"
                icon={<Boxes className="w-5 h-5 text-orange-500" />}
                href="/jubilee"
                status={{
                  is_active: jubileeStatus?.box_spread?.enabled || jubileeStatus?.ic_trading?.enabled,
                  open_positions: (jubileeStatus?.box_spread?.open_positions || 0) + (jubileeStatus?.ic_trading?.open_positions || 0),
                  last_scan_at: jubileeStatus?.last_updated
                }}
                livePnL={{
                  today_pnl: jubileeLivePnL?.net_profit || 0,
                  total_unrealized_pnl: jubileeLivePnL?.ic_unrealized || 0
                }}
                color="orange"
                isLoading={jubileeLoading}
              />
            </div>
          </div>

          {/* Futures Crypto */}
          <div>
            <div className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-2">Futures Crypto</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <BotStatusCard
                name="AGAPE-ETH"
                icon={<TrendingUp className="w-5 h-5 text-purple-500" />}
                href="/futures-crypto"
                status={agapeEthStatus?.data}
                livePnL={{
                  today_pnl: agapeEthStatus?.data?.today_pnl || 0,
                  total_unrealized_pnl: agapeEthStatus?.data?.total_unrealized_pnl || 0
                }}
                color="purple"
                isLoading={agapeEthLoading}
              />
              <BotStatusCard
                name="AGAPE-BTC"
                icon={<TrendingUp className="w-5 h-5 text-orange-500" />}
                href="/futures-crypto"
                status={agapeBtcStatus?.data}
                livePnL={{
                  today_pnl: agapeBtcStatus?.data?.today_pnl || 0,
                  total_unrealized_pnl: agapeBtcStatus?.data?.total_unrealized_pnl || 0
                }}
                color="orange"
                isLoading={agapeBtcLoading}
              />
              <BotStatusCard
                name="AGAPE-XRP"
                icon={<TrendingUp className="w-5 h-5 text-cyan-500" />}
                href="/futures-crypto"
                status={agapeXrpStatus?.data}
                livePnL={{
                  today_pnl: agapeXrpStatus?.data?.today_pnl || 0,
                  total_unrealized_pnl: agapeXrpStatus?.data?.total_unrealized_pnl || 0
                }}
                color="cyan"
                isLoading={agapeXrpLoading}
              />
            </div>
          </div>

          {/* Quick Links */}
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              href="/covenant"
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-primary bg-primary/10 rounded-lg hover:bg-primary/20 transition-colors"
            >
              <Zap className="w-3 h-3" />
              COVENANT View
            </Link>
            <Link
              href="/proverbs"
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-warning bg-warning/10 rounded-lg hover:bg-warning/20 transition-colors"
            >
              <Activity className="w-3 h-3" />
              Governance
            </Link>
            <Link
              href="/logs"
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-text-secondary bg-background-hover rounded-lg hover:bg-background-hover/70 transition-colors"
            >
              View All Logs
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
