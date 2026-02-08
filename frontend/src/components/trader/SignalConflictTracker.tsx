'use client'

import { useState } from 'react'
import { Brain, Zap, AlertTriangle, CheckCircle, XCircle, ChevronDown, ChevronUp, TrendingUp, TrendingDown, Scale } from 'lucide-react'

interface SignalConflict {
  timestamp: string
  scan_id?: string
  ml_said: string
  oracle_said: string
  winner: 'ML' | 'Oracle'
  outcome: 'correct' | 'wrong' | 'pending'
  actual_result?: string
}

interface SignalConflictTrackerProps {
  botName: 'FORTRESS' | 'SOLOMON' | 'PEGASUS'
  conflicts: SignalConflict[]
  totalScansToday: number
  mlWins: number
  oracleWins: number
  mlAccuracy?: number  // Win rate when ML wins conflicts
  oracleAccuracy?: number  // Win rate when Oracle wins conflicts
  isLoading: boolean
}

export default function SignalConflictTracker({
  botName,
  conflicts,
  totalScansToday,
  mlWins,
  oracleWins,
  mlAccuracy,
  oracleAccuracy,
  isLoading
}: SignalConflictTrackerProps) {
  const [expanded, setExpanded] = useState(false)

  const totalConflicts = mlWins + oracleWins
  const conflictRate = totalScansToday > 0 ? ((totalConflicts / totalScansToday) * 100).toFixed(1) : '0.0'

  // Calculate correct decisions
  const mlCorrect = conflicts.filter(c => c.winner === 'ML' && c.outcome === 'correct').length
  const oracleCorrect = conflicts.filter(c => c.winner === 'Oracle' && c.outcome === 'correct').length
  const mlWrong = conflicts.filter(c => c.winner === 'ML' && c.outcome === 'wrong').length
  const oracleWrong = conflicts.filter(c => c.winner === 'Oracle' && c.outcome === 'wrong').length

  if (isLoading) {
    return (
      <div className="bg-[#0a0a0a] rounded-xl p-5 border border-gray-700 animate-pulse">
        <div className="h-6 bg-gray-800 rounded w-48 mb-3" />
        <div className="h-20 bg-gray-800 rounded w-full" />
      </div>
    )
  }

  return (
    <div className="bg-[#0a0a0a] rounded-xl p-5 border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Scale className="w-5 h-5 text-amber-400" />
          <h3 className="text-lg font-bold text-white">ML vs ORACLE CONFLICTS</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">{conflictRate}% of scans had conflicts</span>
          {totalConflicts > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-amber-900/30 text-amber-400 text-xs font-bold">
              {totalConflicts} conflicts
            </span>
          )}
        </div>
      </div>

      {totalConflicts === 0 ? (
        <div className="text-center py-6 text-gray-500">
          <CheckCircle className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>ML and Oracle are in agreement today</p>
          <p className="text-xs mt-1">No signal conflicts detected</p>
        </div>
      ) : (
        <>
          {/* Win Comparison */}
          <div className="grid grid-cols-2 gap-4 mb-4">
            {/* ML Stats */}
            <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-700/30">
              <div className="flex items-center gap-2 mb-3">
                <Brain className="w-5 h-5 text-blue-400" />
                <span className="text-blue-400 font-bold">ML WINS</span>
              </div>
              <div className="text-3xl font-bold text-white mb-1">{mlWins}</div>
              <div className="text-sm text-gray-400">
                {mlCorrect > 0 && (
                  <span className="text-green-400">{mlCorrect} correct</span>
                )}
                {mlCorrect > 0 && mlWrong > 0 && ' / '}
                {mlWrong > 0 && (
                  <span className="text-red-400">{mlWrong} wrong</span>
                )}
              </div>
              {mlAccuracy !== undefined && (
                <div className="mt-2 text-xs">
                  <span className="text-gray-500">Accuracy when ML wins:</span>
                  <span className={`ml-2 font-bold ${mlAccuracy >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                    {mlAccuracy.toFixed(0)}%
                  </span>
                </div>
              )}
            </div>

            {/* Oracle Stats */}
            <div className="bg-purple-900/20 rounded-lg p-4 border border-purple-700/30">
              <div className="flex items-center gap-2 mb-3">
                <Zap className="w-5 h-5 text-purple-400" />
                <span className="text-purple-400 font-bold">ORACLE WINS</span>
              </div>
              <div className="text-3xl font-bold text-white mb-1">{oracleWins}</div>
              <div className="text-sm text-gray-400">
                {oracleCorrect > 0 && (
                  <span className="text-green-400">{oracleCorrect} correct</span>
                )}
                {oracleCorrect > 0 && oracleWrong > 0 && ' / '}
                {oracleWrong > 0 && (
                  <span className="text-red-400">{oracleWrong} wrong</span>
                )}
              </div>
              {oracleAccuracy !== undefined && (
                <div className="mt-2 text-xs">
                  <span className="text-gray-500">Accuracy when Oracle wins:</span>
                  <span className={`ml-2 font-bold ${oracleAccuracy >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                    {oracleAccuracy.toFixed(0)}%
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Win Bar */}
          <div className="mb-4">
            <div className="h-3 rounded-full overflow-hidden bg-gray-800 flex">
              <div
                className="h-full bg-blue-500 transition-all"
                style={{ width: `${totalConflicts > 0 ? (mlWins / totalConflicts) * 100 : 50}%` }}
              />
              <div
                className="h-full bg-purple-500 transition-all"
                style={{ width: `${totalConflicts > 0 ? (oracleWins / totalConflicts) * 100 : 50}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>ML: {totalConflicts > 0 ? ((mlWins / totalConflicts) * 100).toFixed(0) : 0}%</span>
              <span>Oracle: {totalConflicts > 0 ? ((oracleWins / totalConflicts) * 100).toFixed(0) : 0}%</span>
            </div>
          </div>

          {/* Expandable Conflict History */}
          {conflicts.length > 0 && (
            <>
              <button
                onClick={() => setExpanded(!expanded)}
                className="w-full flex items-center justify-between p-2 rounded-lg bg-black/20 hover:bg-black/40 transition"
              >
                <span className="text-sm text-gray-400">
                  {expanded ? 'Hide Conflict History' : `Show Recent Conflicts (${Math.min(conflicts.length, 5)})`}
                </span>
                {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
              </button>

              {expanded && (
                <div className="mt-3 space-y-2">
                  {conflicts.slice(0, 5).map((conflict, i) => (
                    <div key={i} className="bg-black/30 rounded-lg p-3 border border-gray-700">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-gray-500">
                          {new Date(conflict.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Chicago' })} CT
                        </span>
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                            conflict.winner === 'ML' ? 'bg-blue-900/50 text-blue-400' : 'bg-purple-900/50 text-purple-400'
                          }`}>
                            {conflict.winner} won
                          </span>
                          {conflict.outcome === 'correct' && (
                            <CheckCircle className="w-4 h-4 text-green-400" />
                          )}
                          {conflict.outcome === 'wrong' && (
                            <XCircle className="w-4 h-4 text-red-400" />
                          )}
                          {conflict.outcome === 'pending' && (
                            <span className="text-xs text-gray-500">pending</span>
                          )}
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="flex items-center gap-1">
                          <Brain className="w-3 h-3 text-blue-400" />
                          <span className={conflict.winner === 'ML' ? 'text-white' : 'text-gray-500 line-through'}>
                            {conflict.ml_said}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Zap className="w-3 h-3 text-purple-400" />
                          <span className={conflict.winner === 'Oracle' ? 'text-white' : 'text-gray-500 line-through'}>
                            {conflict.oracle_said}
                          </span>
                        </div>
                      </div>
                      {conflict.actual_result && (
                        <div className="mt-2 text-xs text-gray-400">
                          Actual: <span className="text-white">{conflict.actual_result}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Insight */}
          <div className="mt-4 p-3 rounded-lg bg-amber-900/10 border border-amber-700/30">
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5" />
              <div className="text-sm">
                <span className="text-amber-400 font-medium">INSIGHT: </span>
                <span className="text-gray-300">
                  {oracleWins > mlWins
                    ? `Oracle is overriding ML ${((oracleWins / totalConflicts) * 100).toFixed(0)}% of the time. `
                    : `ML is winning ${((mlWins / totalConflicts) * 100).toFixed(0)}% of conflicts. `}
                  {oracleAccuracy !== undefined && oracleAccuracy > (mlAccuracy || 0)
                    ? 'Oracle overrides are more accurate - trust the Oracle.'
                    : mlAccuracy !== undefined && mlAccuracy > (oracleAccuracy || 0)
                    ? 'ML is more accurate when it wins conflicts.'
                    : 'Monitor both signals for patterns.'}
                </span>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
