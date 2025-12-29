'use client'

import { useState } from 'react'
import { Clock, CheckCircle, XCircle, AlertCircle, TrendingUp, TrendingDown, Eye, ChevronDown, ChevronUp, Zap, Target, Brain } from 'lucide-react'

type ActivityType = 'scan' | 'entry' | 'exit' | 'skip' | 'error' | 'adjustment'

interface TimelineActivity {
  id: string
  timestamp: string
  type: ActivityType
  title: string
  description?: string
  pnl?: number
  details?: {
    position_id?: string
    spread_type?: string
    strikes?: string
    contracts?: number
    signal_source?: string
    ml_advice?: string
    ml_confidence?: number
    oracle_advice?: string
    oracle_confidence?: number
    exit_reason?: string
    hold_time?: string
  }
}

interface ActivityTimelineProps {
  activities: TimelineActivity[]
  maxDisplay?: number
  isLoading?: boolean
}

const getActivityConfig = (type: ActivityType) => {
  switch (type) {
    case 'scan':
      return { icon: Eye, color: 'text-blue-400', bg: 'bg-blue-500', line: 'bg-blue-500/30' }
    case 'entry':
      return { icon: TrendingUp, color: 'text-green-400', bg: 'bg-green-500', line: 'bg-green-500/30' }
    case 'exit':
      return { icon: CheckCircle, color: 'text-purple-400', bg: 'bg-purple-500', line: 'bg-purple-500/30' }
    case 'skip':
      return { icon: XCircle, color: 'text-yellow-400', bg: 'bg-yellow-500', line: 'bg-yellow-500/30' }
    case 'error':
      return { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-500', line: 'bg-red-500/30' }
    case 'adjustment':
      return { icon: Zap, color: 'text-orange-400', bg: 'bg-orange-500', line: 'bg-orange-500/30' }
    default:
      return { icon: Clock, color: 'text-gray-400', bg: 'bg-gray-500', line: 'bg-gray-500/30' }
  }
}

export default function ActivityTimeline({ activities, maxDisplay = 10, isLoading = false }: ActivityTimelineProps) {
  const [expanded, setExpanded] = useState(false)
  const [expandedItem, setExpandedItem] = useState<string | null>(null)

  if (isLoading) {
    return (
      <div className="bg-gray-900/50 rounded-lg border border-gray-700 p-4">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-700 rounded w-1/3"></div>
          {[1, 2, 3].map(i => (
            <div key={i} className="flex gap-3">
              <div className="w-3 h-3 rounded-full bg-gray-700"></div>
              <div className="flex-1 space-y-2">
                <div className="h-4 bg-gray-700 rounded w-1/2"></div>
                <div className="h-3 bg-gray-800 rounded w-3/4"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (activities.length === 0) {
    return (
      <div className="bg-gray-900/50 rounded-lg border border-gray-700 p-4 text-center">
        <Clock className="w-8 h-8 text-gray-600 mx-auto mb-2" />
        <p className="text-gray-400 text-sm">No activity yet today</p>
      </div>
    )
  }

  const displayActivities = expanded ? activities : activities.slice(0, maxDisplay)
  const hasMore = activities.length > maxDisplay

  return (
    <div className="bg-gray-900/50 rounded-lg border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 bg-gray-800/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-blue-400" />
          <span className="text-sm font-medium text-white">Activity Timeline</span>
          <span className="text-xs text-gray-400">({activities.length} events)</span>
        </div>
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-gray-400 hover:text-white flex items-center gap-1"
          >
            {expanded ? 'Collapse' : 'Show all'}
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        )}
      </div>

      {/* Timeline */}
      <div className="p-4">
        <div className="relative">
          {displayActivities.map((activity, index) => {
            const config = getActivityConfig(activity.type)
            const Icon = config.icon
            const isLast = index === displayActivities.length - 1
            const isItemExpanded = expandedItem === activity.id

            return (
              <div key={activity.id} className="relative flex gap-4 pb-4">
                {/* Timeline Line */}
                {!isLast && (
                  <div className={`absolute left-[5px] top-6 w-0.5 h-full ${config.line}`}></div>
                )}

                {/* Icon */}
                <div className={`relative z-10 w-3 h-3 rounded-full ${config.bg} mt-1.5 flex-shrink-0`}></div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div
                    className="cursor-pointer"
                    onClick={() => setExpandedItem(isItemExpanded ? null : activity.id)}
                  >
                    {/* Header Row */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Icon className={`w-4 h-4 ${config.color} flex-shrink-0`} />
                        <span className="text-sm font-medium text-white truncate">{activity.title}</span>
                        {activity.pnl !== undefined && (
                          <span className={`text-xs font-bold ${activity.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {activity.pnl >= 0 ? '+' : ''}${activity.pnl.toFixed(2)}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-xs text-gray-500">
                          {new Date(activity.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' })} CT
                        </span>
                        {activity.details && (
                          <span className="text-gray-500">
                            {isItemExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Description */}
                    {activity.description && (
                      <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{activity.description}</p>
                    )}
                  </div>

                  {/* Expanded Details */}
                  {isItemExpanded && activity.details && (
                    <div className="mt-2 p-2 bg-gray-800/50 rounded text-xs space-y-1.5">
                      {activity.details.spread_type && (
                        <div className="flex items-center gap-2">
                          <Target className="w-3 h-3 text-gray-400" />
                          <span className="text-gray-400">Spread:</span>
                          <span className="text-white">{activity.details.spread_type}</span>
                          {activity.details.strikes && (
                            <span className="text-gray-300">@ {activity.details.strikes}</span>
                          )}
                        </div>
                      )}
                      {activity.details.signal_source && (
                        <div className="flex items-center gap-2">
                          <Brain className="w-3 h-3 text-gray-400" />
                          <span className="text-gray-400">Signal:</span>
                          <span className={`${activity.details.signal_source.includes('override') ? 'text-amber-400' : 'text-blue-400'}`}>
                            {activity.details.signal_source}
                          </span>
                        </div>
                      )}
                      {activity.details.ml_advice && (
                        <div className="flex items-center gap-2">
                          <span className="text-gray-400">ML:</span>
                          <span className={activity.details.ml_advice === 'STAY_OUT' ? 'text-red-400' : 'text-green-400'}>
                            {activity.details.ml_advice}
                          </span>
                          {activity.details.ml_confidence && (
                            <span className="text-gray-500">({(activity.details.ml_confidence * 100).toFixed(0)}%)</span>
                          )}
                        </div>
                      )}
                      {activity.details.oracle_advice && (
                        <div className="flex items-center gap-2">
                          <span className="text-gray-400">Oracle:</span>
                          <span className={activity.details.oracle_advice === 'SKIP_TODAY' ? 'text-red-400' : 'text-green-400'}>
                            {activity.details.oracle_advice}
                          </span>
                          {activity.details.oracle_confidence && (
                            <span className="text-gray-500">({(activity.details.oracle_confidence * 100).toFixed(0)}%)</span>
                          )}
                        </div>
                      )}
                      {activity.details.exit_reason && (
                        <div className="flex items-center gap-2">
                          <span className="text-gray-400">Exit:</span>
                          <span className="text-purple-400">{activity.details.exit_reason}</span>
                        </div>
                      )}
                      {activity.details.hold_time && (
                        <div className="flex items-center gap-2">
                          <Clock className="w-3 h-3 text-gray-400" />
                          <span className="text-gray-400">Held:</span>
                          <span className="text-white">{activity.details.hold_time}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
