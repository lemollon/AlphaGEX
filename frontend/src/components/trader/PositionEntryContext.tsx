'use client'

import { Brain, Zap, Shield, TrendingUp, TrendingDown, Target, Clock, DollarSign, Activity } from 'lucide-react'

interface PositionEntryContextProps {
  // Position basics
  positionId: string
  spreadType: string
  ticker: string
  strikes: string

  // Entry timing
  entryTime: string
  entryPrice: number

  // Market context at entry
  spotAtEntry: number
  vixAtEntry?: number
  gexRegimeAtEntry?: string
  putWallAtEntry?: number
  callWallAtEntry?: number
  netGexAtEntry?: number

  // Signals at entry
  mlDirectionAtEntry?: string
  mlConfidenceAtEntry?: number
  mlWinProbAtEntry?: number
  oracleAdviceAtEntry?: string
  oracleConfidenceAtEntry?: number
  oracleWinProbAtEntry?: number

  // Greeks at entry
  entryDelta?: number
  entryGamma?: number
  entryTheta?: number
  entryVega?: number

  // Current comparison
  currentSpot?: number
  currentVix?: number
  currentGexRegime?: string
  currentDelta?: number

  // Signal source
  signalSource?: string  // "ML", "Prophet", "Prophet (override)"
  wasOverride?: boolean
}

export default function PositionEntryContext({
  positionId,
  spreadType,
  ticker,
  strikes,
  entryTime,
  entryPrice,
  spotAtEntry,
  vixAtEntry,
  gexRegimeAtEntry,
  putWallAtEntry,
  callWallAtEntry,
  netGexAtEntry,
  mlDirectionAtEntry,
  mlConfidenceAtEntry,
  mlWinProbAtEntry,
  oracleAdviceAtEntry,
  oracleConfidenceAtEntry,
  oracleWinProbAtEntry,
  entryDelta,
  entryGamma,
  entryTheta,
  entryVega,
  currentSpot,
  currentVix,
  currentGexRegime,
  currentDelta,
  signalSource,
  wasOverride
}: PositionEntryContextProps) {
  // Calculate changes
  const spotChange = currentSpot && spotAtEntry ? ((currentSpot - spotAtEntry) / spotAtEntry * 100) : 0
  const vixChange = currentVix && vixAtEntry ? (currentVix - vixAtEntry) : 0
  const deltaChange = currentDelta && entryDelta ? (currentDelta - entryDelta) : 0

  // Distance to walls at entry
  const distToPutWall = putWallAtEntry && spotAtEntry ? (spotAtEntry - putWallAtEntry) : null
  const distToCallWall = callWallAtEntry && spotAtEntry ? (callWallAtEntry - spotAtEntry) : null

  return (
    <div className="bg-[#0a0a0a] rounded-xl border border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-purple-900/30 to-[#0a0a0a] p-4 border-b border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-bold text-white">WHY THIS POSITION?</h3>
            <span className="text-gray-400 text-sm">{ticker} {spreadType?.replace(/_/g, ' ')} {strikes}</span>
          </div>
          {signalSource && (
            <span className={`px-3 py-1 rounded-full text-sm font-bold ${
              wasOverride ? 'bg-amber-900/50 text-amber-400 border border-amber-500/50' :
              signalSource.includes('ML') ? 'bg-blue-900/50 text-blue-400' :
              'bg-purple-900/50 text-purple-400'
            }`}>
              {signalSource}
              {wasOverride && ' (OVERRIDE)'}
            </span>
          )}
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Entry Timing */}
        <div className="flex items-center gap-2 text-sm">
          <Clock className="w-4 h-4 text-gray-500" />
          <span className="text-gray-400">Entered:</span>
          <span className="text-white">{new Date(entryTime).toLocaleString('en-US', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
          })}</span>
          <span className="text-gray-500">at ${entryPrice?.toFixed(2)}</span>
        </div>

        {/* Signal Sources at Entry */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* ML Signal */}
          <div className="bg-blue-900/10 rounded-lg p-3 border border-blue-700/30">
            <div className="flex items-center gap-2 mb-2">
              <Brain className="w-4 h-4 text-blue-400" />
              <span className="text-blue-400 text-sm font-bold">ML AT ENTRY</span>
            </div>
            {mlDirectionAtEntry ? (
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  {mlDirectionAtEntry === 'BULLISH' || mlDirectionAtEntry === 'UP' ? (
                    <TrendingUp className="w-4 h-4 text-green-400" />
                  ) : mlDirectionAtEntry === 'BEARISH' || mlDirectionAtEntry === 'DOWN' ? (
                    <TrendingDown className="w-4 h-4 text-red-400" />
                  ) : (
                    <Target className="w-4 h-4 text-gray-400" />
                  )}
                  <span className={`font-bold ${
                    mlDirectionAtEntry.includes('BULL') || mlDirectionAtEntry === 'UP' ? 'text-green-400' :
                    mlDirectionAtEntry.includes('BEAR') || mlDirectionAtEntry === 'DOWN' ? 'text-red-400' : 'text-gray-400'
                  }`}>
                    {mlDirectionAtEntry}
                  </span>
                </div>
                <div className="text-xs text-gray-400 space-y-0.5">
                  {mlConfidenceAtEntry !== undefined && (
                    <div>Confidence: <span className="text-white font-mono">{(mlConfidenceAtEntry * 100).toFixed(0)}%</span></div>
                  )}
                  {mlWinProbAtEntry !== undefined && (
                    <div>Win Prob: <span className="text-white font-mono">{(mlWinProbAtEntry * 100).toFixed(0)}%</span></div>
                  )}
                </div>
              </div>
            ) : (
              <span className="text-gray-500 text-sm">No ML data</span>
            )}
          </div>

          {/* Prophet Signal */}
          <div className="bg-purple-900/10 rounded-lg p-3 border border-purple-700/30">
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-4 h-4 text-purple-400" />
              <span className="text-purple-400 text-sm font-bold">PROPHET AT ENTRY</span>
            </div>
            {oracleAdviceAtEntry ? (
              <div className="space-y-1">
                <span className={`font-bold ${
                  oracleAdviceAtEntry.includes('TRADE') ? 'text-green-400' : 'text-yellow-400'
                }`}>
                  {oracleAdviceAtEntry}
                </span>
                <div className="text-xs text-gray-400 space-y-0.5">
                  {oracleConfidenceAtEntry !== undefined && (
                    <div>Confidence: <span className="text-white font-mono">{(oracleConfidenceAtEntry * 100).toFixed(0)}%</span></div>
                  )}
                  {oracleWinProbAtEntry !== undefined && (
                    <div>Win Prob: <span className="text-white font-mono">{(oracleWinProbAtEntry * 100).toFixed(0)}%</span></div>
                  )}
                </div>
              </div>
            ) : (
              <span className="text-gray-500 text-sm">No Prophet data</span>
            )}
          </div>
        </div>

        {/* Market Context at Entry */}
        <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-cyan-400" />
            <span className="text-cyan-400 text-sm font-bold">MARKET AT ENTRY</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <span className="text-gray-500 block text-xs">Spot</span>
              <span className="text-white font-mono">${spotAtEntry?.toFixed(2)}</span>
              {currentSpot && (
                <span className={`text-xs ml-1 ${spotChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ({spotChange >= 0 ? '+' : ''}{spotChange.toFixed(2)}%)
                </span>
              )}
            </div>
            {vixAtEntry !== undefined && (
              <div>
                <span className="text-gray-500 block text-xs">VIX</span>
                <span className="text-white font-mono">{vixAtEntry.toFixed(2)}</span>
                {currentVix && (
                  <span className={`text-xs ml-1 ${vixChange <= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ({vixChange >= 0 ? '+' : ''}{vixChange.toFixed(2)})
                  </span>
                )}
              </div>
            )}
            {gexRegimeAtEntry && (
              <div>
                <span className="text-gray-500 block text-xs">GEX Regime</span>
                <span className={`font-mono ${
                  gexRegimeAtEntry === 'POSITIVE' ? 'text-green-400' : 'text-orange-400'
                }`}>
                  {gexRegimeAtEntry}
                </span>
                {currentGexRegime && currentGexRegime !== gexRegimeAtEntry && (
                  <span className="text-xs ml-1 text-amber-400">→ {currentGexRegime}</span>
                )}
              </div>
            )}
            {netGexAtEntry !== undefined && (
              <div>
                <span className="text-gray-500 block text-xs">Net GEX</span>
                <span className="text-white font-mono">{(netGexAtEntry / 1e9).toFixed(2)}B</span>
              </div>
            )}
          </div>

          {/* Wall Distances */}
          {(distToPutWall !== null || distToCallWall !== null) && (
            <div className="mt-3 pt-3 border-t border-gray-700/50 grid grid-cols-2 gap-3 text-sm">
              {distToPutWall !== null && (
                <div>
                  <span className="text-gray-500 block text-xs">Put Wall Distance</span>
                  <span className="text-green-400 font-mono">{distToPutWall.toFixed(0)} pts buffer</span>
                </div>
              )}
              {distToCallWall !== null && (
                <div>
                  <span className="text-gray-500 block text-xs">Call Wall Distance</span>
                  <span className="text-red-400 font-mono">{distToCallWall.toFixed(0)} pts to wall</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Greeks at Entry */}
        {(entryDelta !== undefined || entryGamma !== undefined || entryTheta !== undefined) && (
          <div className="bg-black/30 rounded-lg p-3 border border-gray-700">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-yellow-400" />
              <span className="text-yellow-400 text-sm font-bold">GREEKS AT ENTRY</span>
            </div>
            <div className="grid grid-cols-4 gap-3 text-sm">
              {entryDelta !== undefined && (
                <div>
                  <span className="text-gray-500 block text-xs">Delta</span>
                  <span className="text-white font-mono">{entryDelta.toFixed(3)}</span>
                  {currentDelta !== undefined && (
                    <span className={`text-xs block ${Math.abs(deltaChange) > 0.1 ? 'text-amber-400' : 'text-gray-500'}`}>
                      now: {currentDelta.toFixed(3)}
                    </span>
                  )}
                </div>
              )}
              {entryGamma !== undefined && (
                <div>
                  <span className="text-gray-500 block text-xs">Gamma</span>
                  <span className="text-white font-mono">{entryGamma.toFixed(4)}</span>
                </div>
              )}
              {entryTheta !== undefined && (
                <div>
                  <span className="text-gray-500 block text-xs">Theta</span>
                  <span className="text-red-400 font-mono">{entryTheta.toFixed(2)}</span>
                </div>
              )}
              {entryVega !== undefined && (
                <div>
                  <span className="text-gray-500 block text-xs">Vega</span>
                  <span className="text-white font-mono">{entryVega.toFixed(3)}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Trade Story Summary */}
        <div className="bg-gradient-to-r from-green-900/10 to-blue-900/10 rounded-lg p-3 border border-green-700/30">
          <div className="flex items-start gap-2">
            <DollarSign className="w-4 h-4 text-green-400 mt-0.5" />
            <div className="text-sm text-gray-300">
              <span className="text-green-400 font-medium">TRADE STORY: </span>
              Entered {spreadType?.replace(/_/g, ' ')}
              {mlDirectionAtEntry && ` on ${mlDirectionAtEntry} ML signal`}
              {mlConfidenceAtEntry && ` (${(mlConfidenceAtEntry * 100).toFixed(0)}% confidence)`}
              {oracleAdviceAtEntry && `, Prophet said ${oracleAdviceAtEntry}`}
              {vixAtEntry && `. VIX was ${vixAtEntry.toFixed(1)}`}
              {gexRegimeAtEntry && `, GEX ${gexRegimeAtEntry}`}
              {distToPutWall && `, ${distToPutWall.toFixed(0)} pts above put wall`}.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
