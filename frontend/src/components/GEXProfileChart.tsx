'use client'

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine, Cell } from 'recharts'

interface GEXLevel {
  strike: number
  call_gex: number
  put_gex: number
  total_gex: number
  call_oi?: number
  put_oi?: number
  pcr?: number
}

interface GEXProfileChartProps {
  data: GEXLevel[]
  spotPrice?: number
  flipPoint?: number
  callWall?: number
  putWall?: number
  height?: number
}

export default function GEXProfileChart({
  data,
  spotPrice,
  flipPoint,
  callWall,
  putWall,
  height = 600
}: GEXProfileChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        className="w-full bg-background-deep rounded-lg flex items-center justify-center border border-border"
        style={{ height: `${height}px` }}
      >
        <p className="text-text-muted">No GEX data available</p>
      </div>
    )
  }

  // Transform data - show CALL and PUT separately (NOT net) so you see where MMs have exposure
  const chartData = data.map(level => {
    // Convert to millions - keep ACTUAL values (not normalized)
    const call_g = level.call_gex / 1e6
    const put_g = Math.abs(level.put_gex) / 1e6  // Show as positive for stacked view

    return {
      strike: level.strike,
      strikeLabel: `$${level.strike.toFixed(0)}`,
      callGamma: call_g,  // Positive values - resistance above
      putGamma: -put_g,    // Negative values - support below
      netGamma: (level.call_gex - Math.abs(level.put_gex)) / 1e6,  // TRUE net gamma
      isWall: (call_g > 100 || put_g > 100)  // Flag major concentrations
    }
  })

  // Find the REAL max gamma (not normalized - show actual scale!)
  const maxCallGamma = Math.max(...chartData.map(d => d.callGamma))
  const maxPutGamma = Math.abs(Math.min(...chartData.map(d => d.putGamma)))
  const absoluteMax = Math.max(maxCallGamma, maxPutGamma)

  // Use FIXED scale based on data (not normalized to fit) so you see the real concentrations
  const yAxisDomain = [-absoluteMax * 1.2, absoluteMax * 1.2]

  // Find top 3 call and put walls for highlighting
  const sortedByCallGamma = [...chartData].sort((a, b) => b.callGamma - a.callGamma)
  const sortedByPutGamma = [...chartData].sort((a, b) => a.putGamma - b.putGamma)
  const topCallWalls = new Set(sortedByCallGamma.slice(0, 3).map(d => d.strike))
  const topPutWalls = new Set(sortedByPutGamma.slice(0, 3).map(d => d.strike))

  // Custom tooltip with ACTIONABLE info
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload
      const callGamma = data.callGamma
      const putGamma = Math.abs(data.putGamma)
      const netGamma = data.netGamma
      const isTopCall = topCallWalls.has(data.strike)
      const isTopPut = topPutWalls.has(data.strike)

      return (
        <div className="bg-background-deep border-2 border-primary rounded-lg p-4 shadow-xl min-w-[280px]">
          <div className="flex items-center justify-between mb-3">
            <p className="font-bold text-text-primary text-lg">${label}</p>
            {(isTopCall || isTopPut) && (
              <span className="px-2 py-1 rounded text-xs font-bold bg-warning text-background">
                🎯 WALL
              </span>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-success text-sm font-medium">Call Gamma:</span>
              <span className="text-success font-bold">${callGamma.toFixed(1)}M</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-danger text-sm font-medium">Put Gamma:</span>
              <span className="text-danger font-bold">${putGamma.toFixed(1)}M</span>
            </div>
            <div className="border-t border-border my-2"></div>
            <div className="flex justify-between items-center">
              <span className="text-primary text-sm font-bold">Net Gamma:</span>
              <span className={`font-bold ${netGamma > 0 ? 'text-success' : 'text-danger'}`}>
                ${netGamma.toFixed(1)}M
              </span>
            </div>
          </div>

          <div className="mt-3 pt-3 border-t border-border">
            <p className="text-xs text-text-muted">
              {isTopCall && "🔴 Major RESISTANCE - price will struggle above"}
              {isTopPut && "🟢 Major SUPPORT - price will hold above"}
              {!isTopCall && !isTopPut && netGamma > 50 && "Moderate call wall"}
              {!isTopCall && !isTopPut && netGamma < -50 && "Moderate put wall"}
              {!isTopCall && !isTopPut && Math.abs(netGamma) <= 50 && "Minimal gamma"}
            </p>
          </div>
        </div>
      )
    }
    return null
  }

  // Calculate label positions for overlay (always visible)
  const calculateLabelPosition = (strikeValue: number) => {
    if (!chartData || chartData.length === 0) return 0
    const minStrike = Math.min(...chartData.map(d => d.strike))
    const maxStrike = Math.max(...chartData.map(d => d.strike))
    const range = maxStrike - minStrike
    if (range === 0) return 50 // Center if no range
    const position = ((strikeValue - minStrike) / range) * 100
    return Math.max(0, Math.min(100, position)) // Clamp between 0-100%
  }

  return (
    <div className="w-full space-y-4">
      {/* Stats Bar - Show what the chart means for making money */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-success/10 border border-success/20 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-success"></div>
            <span className="text-xs font-semibold text-success">🔴 CALL WALL (Resistance)</span>
          </div>
          <p className="text-2xl font-bold text-success">${maxCallGamma.toFixed(0)}M</p>
          {callWall && callWall > 0 && (
            <p className="text-sm font-semibold text-success mt-1">Strike: ${callWall.toFixed(2)}</p>
          )}
          <p className="text-xs text-text-muted mt-1">Price gets rejected here</p>
        </div>

        <div className="bg-danger/10 border border-danger/20 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-danger"></div>
            <span className="text-xs font-semibold text-danger">🟢 PUT WALL (Support)</span>
          </div>
          <p className="text-2xl font-bold text-danger">${maxPutGamma.toFixed(0)}M</p>
          {putWall && putWall > 0 && (
            <p className="text-sm font-semibold text-danger mt-1">Strike: ${putWall.toFixed(2)}</p>
          )}
          <p className="text-xs text-text-muted mt-1">Price finds support here</p>
        </div>

        <div className="bg-primary/10 border border-primary/20 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-3 h-3 rounded-full bg-primary"></div>
            <span className="text-xs font-semibold text-primary">NET GAMMA</span>
          </div>
          <p className="text-2xl font-bold text-primary">
            {chartData.reduce((sum, d) => sum + d.netGamma, 0).toFixed(0)}M
          </p>
          <p className="text-xs text-text-muted mt-1">
            {chartData.reduce((sum, d) => sum + d.netGamma, 0) > 0 ? "Positive = Range bound" : "Negative = Volatile"}
          </p>
        </div>
      </div>

      {/* NET GEX Chart - MAIN CHART */}
      <div className="bg-background-deep rounded-lg p-4 border-2 border-primary/50">
        <div className="mb-4">
          <h3 className="text-lg font-bold text-text-primary">📊 NET Gamma Profile</h3>
          <p className="text-sm text-text-secondary mt-1">
            Blue = positive net gamma (calls dominant) | Red = negative net gamma (puts dominant)
          </p>
        </div>

        {/* ALWAYS VISIBLE LABELS - Absolute positioned overlay */}
        <div className="relative">
          {/* Label Overlay Container */}
          <div className="absolute top-2 left-0 right-0 h-8 z-10 pointer-events-none flex items-center" style={{ marginLeft: '20px', marginRight: '50px' }}>
            {/* Spot Price Label */}
            {spotPrice && (
              <div
                className="absolute transform -translate-x-1/2"
                style={{ left: `${calculateLabelPosition(spotPrice)}%` }}
              >
                <span className="text-xs font-bold px-2 py-1 rounded" style={{
                  color: '#fbbf24',
                  backgroundColor: 'rgba(0,0,0,0.7)',
                  textShadow: '0 0 3px rgba(0,0,0,1)',
                  whiteSpace: 'nowrap'
                }}>
                  📍 ${spotPrice.toFixed(2)}
                </span>
              </div>
            )}

            {/* Flip Point Label */}
            {flipPoint && flipPoint > 0 && (
              <div
                className="absolute transform -translate-x-1/2"
                style={{ left: `${calculateLabelPosition(flipPoint)}%` }}
              >
                <span className="text-xs font-bold px-2 py-1 rounded" style={{
                  color: '#fb923c',
                  backgroundColor: 'rgba(0,0,0,0.7)',
                  textShadow: '0 0 3px rgba(0,0,0,1)',
                  whiteSpace: 'nowrap'
                }}>
                  ⚡ ${flipPoint.toFixed(2)}
                </span>
              </div>
            )}

            {/* Call Wall Label */}
            {callWall && callWall > 0 && (
              <div
                className="absolute transform -translate-x-1/2"
                style={{ left: `${calculateLabelPosition(callWall)}%` }}
              >
                <span className="text-xs font-bold px-2 py-1 rounded" style={{
                  color: '#10b981',
                  backgroundColor: 'rgba(0,0,0,0.7)',
                  textShadow: '0 0 3px rgba(0,0,0,1)',
                  whiteSpace: 'nowrap'
                }}>
                  🔴 ${callWall.toFixed(0)}
                </span>
              </div>
            )}

            {/* Put Wall Label */}
            {putWall && putWall > 0 && (
              <div
                className="absolute transform -translate-x-1/2"
                style={{ left: `${calculateLabelPosition(putWall)}%` }}
              >
                <span className="text-xs font-bold px-2 py-1 rounded" style={{
                  color: '#ef4444',
                  backgroundColor: 'rgba(0,0,0,0.7)',
                  textShadow: '0 0 3px rgba(0,0,0,1)',
                  whiteSpace: 'nowrap'
                }}>
                  🟢 ${putWall.toFixed(0)}
                </span>
              </div>
            )}
          </div>

          {/* Chart */}
          <ResponsiveContainer width="100%" height={height}>
          <BarChart
            data={chartData}
            margin={{ top: 80, right: 50, left: 20, bottom: 80 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1f2e" />
            <XAxis
              dataKey="strike"
              stroke="#9ca3af"
              angle={-45}
              textAnchor="end"
              height={80}
              tick={{ fontSize: 11 }}
              tickFormatter={(value) => `$${value.toFixed(0)}`}
            />
            <YAxis
              stroke="#9ca3af"
              tick={{ fontSize: 11 }}
              domain={yAxisDomain}
              label={{ value: 'Net Gamma ($M)', angle: -90, position: 'insideLeft', fill: '#9ca3af', fontSize: 12 }}
              tickFormatter={(value) => `${value.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(59, 130, 246, 0.1)' }} />
            <Legend
              wrapperStyle={{ paddingTop: '15px' }}
              iconType="square"
            />

            {/* Zero line - thicker for emphasis */}
            <ReferenceLine y={0} stroke="#6b7280" strokeWidth={2} />

            {/* Spot price - WHERE WE ARE NOW */}
            {spotPrice && (
              <ReferenceLine
                x={spotPrice}
                stroke="#fbbf24"
                strokeWidth={3}
                strokeDasharray="5 5"
              />
            )}

            {/* Flip point - REGIME CHANGE */}
            {flipPoint && flipPoint > 0 && (
              <ReferenceLine
                x={flipPoint}
                stroke="#fb923c"
                strokeWidth={3}
                strokeDasharray="5 5"
              />
            )}

            {/* Call wall - RESISTANCE */}
            {callWall && callWall > 0 && (
              <ReferenceLine
                x={callWall}
                stroke="#10b981"
                strokeWidth={3}
                strokeDasharray="3 3"
              />
            )}

            {/* Put wall - SUPPORT */}
            {putWall && putWall > 0 && (
              <ReferenceLine
                x={putWall}
                stroke="#ef4444"
                strokeWidth={3}
                strokeDasharray="3 3"
              />
            )}

            {/* NET GAMMA BAR - color based on positive/negative */}
            <Bar dataKey="netGamma" name="Net Gamma">
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.netGamma > 0 ? '#3b82f6' : '#ef4444'}
                  opacity={0.8}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        </div> {/* Close relative wrapper for labels */}
      </div>

      {/* Separate Call/Put GEX Chart - SECONDARY */}
      <div className="bg-background-deep rounded-lg p-4 border border-border">
        <div className="mb-4">
          <h3 className="text-lg font-bold text-text-primary">Call vs Put Gamma Breakdown</h3>
          <p className="text-sm text-text-secondary mt-1">
            Green bars = Call walls (resistance) | Red bars = Put walls (support)
          </p>
        </div>
        <ResponsiveContainer width="100%" height={height * 0.6}>
          <BarChart
            data={chartData}
            margin={{ top: 60, right: 50, left: 20, bottom: 80 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1f2e" />
            <XAxis
              dataKey="strike"
              stroke="#9ca3af"
              angle={-45}
              textAnchor="end"
              height={80}
              tick={{ fontSize: 11 }}
              tickFormatter={(value) => `$${value.toFixed(0)}`}
            />
            <YAxis
              stroke="#9ca3af"
              tick={{ fontSize: 11 }}
              domain={yAxisDomain}
              label={{ value: 'Gamma Exposure ($M)', angle: -90, position: 'insideLeft', fill: '#9ca3af', fontSize: 12 }}
              tickFormatter={(value) => `${value.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(59, 130, 246, 0.1)' }} />
            <Legend
              wrapperStyle={{ paddingTop: '15px' }}
              iconType="square"
              formatter={(value) => {
                if (value === 'callGamma') return 'Call Gamma (Resistance)'
                if (value === 'putGamma') return 'Put Gamma (Support)'
                return value
              }}
            />

            {/* Zero line */}
            <ReferenceLine y={0} stroke="#6b7280" strokeWidth={2} />

            {/* Reference lines - lighter weight for secondary chart */}
            {spotPrice && (
              <ReferenceLine
                x={spotPrice}
                stroke="#fbbf24"
                strokeWidth={2}
                strokeDasharray="5 5"
              />
            )}
            {flipPoint && flipPoint > 0 && (
              <ReferenceLine
                x={flipPoint}
                stroke="#fb923c"
                strokeWidth={2}
                strokeDasharray="5 5"
              />
            )}
            {callWall && callWall > 0 && (
              <ReferenceLine
                x={callWall}
                stroke="#10b981"
                strokeWidth={2}
                strokeDasharray="3 3"
              />
            )}
            {putWall && putWall > 0 && (
              <ReferenceLine
                x={putWall}
                stroke="#ef4444"
                strokeWidth={2}
                strokeDasharray="3 3"
              />
            )}

            {/* Show call and put gamma separately */}
            <Bar dataKey="callGamma" name="callGamma" fill="#10b981" opacity={0.8} />
            <Bar dataKey="putGamma" name="putGamma" fill="#ef4444" opacity={0.8} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Actionable Legend */}
      <div className="bg-background-hover rounded-lg p-4 border border-border">
        <h4 className="font-bold text-text-primary mb-2">💰 How to Use This Chart to Make Money:</h4>
        <ul className="space-y-1 text-sm text-text-secondary">
          <li>• <span className="text-success font-semibold">Green bars</span> = Call gamma walls = <span className="text-warning">SELL here</span> (resistance)</li>
          <li>• <span className="text-danger font-semibold">Red bars</span> = Put gamma walls = <span className="text-success">BUY here</span> (support)</li>
          <li>• <span className="text-primary font-semibold">Bigger bars</span> = Stronger levels where price will get stuck</li>
          <li>• <span className="text-warning font-semibold">Flip point</span> = Regime change - volatility shifts when crossed</li>
          <li>• Price tends to <span className="font-semibold">ping-pong between walls</span> - trade the range!</li>
        </ul>
      </div>
    </div>
  )
}
