'use client'

import { useState } from 'react'
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
  Zap
} from 'lucide-react'
import {
  useARESStatus,
  useATHENAStatus,
  usePEGASUSStatus,
  useARESLivePnL,
  useATHENALivePnL,
  usePEGASUSLivePnL
} from '@/lib/hooks/useMarketData'

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

function BotStatusCard({ name, icon, href, status, livePnL, color, isLoading }: BotStatusCardProps) {
  const isActive = status?.is_active || status?.bot_status === 'ACTIVE' || status?.status === 'active'
  const hasOpenPositions = (status?.open_positions_count || 0) > 0 || (status?.positions?.open?.length || 0) > 0
  const openPositionsCount = status?.open_positions_count || status?.positions?.open?.length || 0

  // Get P&L values
  const totalPnL = livePnL?.total_unrealized_pnl || livePnL?.unrealized_pnl || status?.total_pnl || 0
  const todayPnL = livePnL?.today_pnl || status?.today_pnl || 0

  const colorClasses: Record<string, { bg: string; border: string; text: string }> = {
    blue: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', text: 'text-blue-500' },
    purple: { bg: 'bg-purple-500/10', border: 'border-purple-500/30', text: 'text-purple-500' },
    amber: { bg: 'bg-amber-500/10', border: 'border-amber-500/30', text: 'text-amber-500' },
  }

  const colors = colorClasses[color] || colorClasses.blue

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
}

export default function BotStatusOverview() {
  const [expanded, setExpanded] = useState(true)

  const { data: aresStatus, isLoading: aresLoading, mutate: refreshAres } = useARESStatus()
  const { data: athenaStatus, isLoading: athenaLoading, mutate: refreshAthena } = useATHENAStatus()
  const { data: pegasusStatus, isLoading: pegasusLoading, mutate: refreshPegasus } = usePEGASUSStatus()

  const { data: aresLivePnL } = useARESLivePnL()
  const { data: athenaLivePnL } = useATHENALivePnL()
  const { data: pegasusLivePnL } = usePEGASUSLivePnL()

  const refreshAll = () => {
    refreshAres()
    refreshAthena()
    refreshPegasus()
  }

  // Calculate total P&L across all bots
  const totalTodayPnL = (aresLivePnL?.data?.today_pnl || 0) +
                        (athenaLivePnL?.data?.today_pnl || 0) +
                        (pegasusLivePnL?.data?.today_pnl || 0)

  const totalUnrealizedPnL = (aresLivePnL?.data?.total_unrealized_pnl || 0) +
                             (athenaLivePnL?.data?.total_unrealized_pnl || 0) +
                             (pegasusLivePnL?.data?.total_unrealized_pnl || 0)

  // Count active bots
  const activeBots = [
    aresStatus?.data?.is_active || aresStatus?.data?.bot_status === 'ACTIVE',
    athenaStatus?.data?.is_active || athenaStatus?.data?.bot_status === 'ACTIVE',
    pegasusStatus?.data?.is_active || pegasusStatus?.data?.status === 'active'
  ].filter(Boolean).length

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
                {activeBots}/3 active
              </span>
              <span className={totalTodayPnL >= 0 ? 'text-success' : 'text-danger'}>
                Today: {totalTodayPnL >= 0 ? '+' : ''}${totalTodayPnL.toFixed(0)}
              </span>
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

          {/* Bot Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <BotStatusCard
              name="ARES"
              icon={<Sword className="w-5 h-5 text-blue-500" />}
              href="/ares"
              status={aresStatus?.data}
              livePnL={aresLivePnL?.data}
              color="blue"
              isLoading={aresLoading}
            />
            <BotStatusCard
              name="ATHENA"
              icon={<Target className="w-5 h-5 text-purple-500" />}
              href="/athena"
              status={athenaStatus?.data}
              livePnL={athenaLivePnL?.data}
              color="purple"
              isLoading={athenaLoading}
            />
            <BotStatusCard
              name="PEGASUS"
              icon={<Shield className="w-5 h-5 text-amber-500" />}
              href="/pegasus"
              status={pegasusStatus?.data}
              livePnL={pegasusLivePnL?.data}
              color="amber"
              isLoading={pegasusLoading}
            />
          </div>

          {/* Quick Links */}
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              href="/nexus"
              className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-primary bg-primary/10 rounded-lg hover:bg-primary/20 transition-colors"
            >
              <Zap className="w-3 h-3" />
              NEXUS View
            </Link>
            <Link
              href="/solomon"
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
