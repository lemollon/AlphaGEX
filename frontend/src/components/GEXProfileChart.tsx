'use client'

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts'

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

  // Transform data EXACTLY like visualization_and_plans.py lines 56-62
  const chartData = data.map(level => {
    // Convert to millions like original Plotly code
    const call_g = level.call_gex / 1e6
    const put_g = -Math.abs(level.put_gex) / 1e6  // Make negative for chart

    return {
      strike: level.strike,
      strikeLabel: `$${level.strike.toFixed(0)}`,
      callGamma: call_g,
      putGamma: put_g,
      totalGamma: call_g + put_g  // Calculate total like line 62: call_g + put_g
    }
  })

  // Find min/max for Y-axis
  const allValues = chartData.flatMap(d => [d.callGamma, d.putGamma, d.totalGamma])
  const maxValue = Math.max(...allValues.map(Math.abs))
  const yAxisDomain = [-maxValue * 1.1, maxValue * 1.1]

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-background-deep border border-border rounded-lg p-3 shadow-lg">
          <p className="font-semibold text-text-primary mb-2">Strike: ${label}</p>
          {payload.map((entry: any, index: number) => (
            <p key={index} style={{ color: entry.color }} className="text-sm">
              {entry.name}: ${Math.abs(entry.value).toFixed(1)}M
            </p>
          ))}
        </div>
      )
    }
    return null
  }

  return (
    <div className="w-full">
      {/* Net Gamma Profile - ONLY chart matching Plotly visualization_and_plans.py */}
      <div className="bg-background-deep rounded-lg p-4 border border-border">
        <h3 className="text-sm font-semibold text-text-secondary mb-3">Net Gamma Profile</h3>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart
            data={chartData}
            margin={{ top: 30, right: 50, left: 20, bottom: 80 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#1a1f2e" />
            <XAxis
              dataKey="strike"
              stroke="#9ca3af"
              angle={-45}
              textAnchor="end"
              height={80}
              tick={{ fontSize: 12 }}
              tickFormatter={(value) => `$${value.toFixed(0)}`}
            />
            <YAxis
              stroke="#9ca3af"
              tick={{ fontSize: 12 }}
              domain={yAxisDomain}
              label={{ value: 'Net Gamma ($M)', angle: -90, position: 'insideLeft', fill: '#9ca3af' }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ paddingTop: '10px' }} iconType="square" />

            {/* Zero line */}
            <ReferenceLine y={0} stroke="#6b7280" strokeWidth={1} />

            {/* Spot price reference line (yellow, dashed) - matching Plotly line 120-162 */}
            {spotPrice && (
              <ReferenceLine
                x={spotPrice}
                stroke="#fbbf24"
                strokeWidth={2}
                strokeDasharray="5 5"
                label={{
                  value: `Spot: $${spotPrice.toFixed(2)}`,
                  position: 'top',
                  fill: '#fbbf24',
                  fontSize: 11,
                  fontWeight: 'bold'
                }}
              />
            )}

            {/* Flip point reference line (orange, dashed) - matching Plotly */}
            {flipPoint && flipPoint > 0 && (
              <ReferenceLine
                x={flipPoint}
                stroke="#fb923c"
                strokeWidth={2}
                strokeDasharray="5 5"
                label={{
                  value: `Flip: $${flipPoint.toFixed(2)}`,
                  position: 'top',
                  fill: '#fb923c',
                  fontSize: 11,
                  fontWeight: 'bold',
                  offset: 10
                }}
              />
            )}

            {/* Call wall reference line (green, dotted) - matching Plotly */}
            {callWall && callWall > 0 && (
              <ReferenceLine
                x={callWall}
                stroke="#10b981"
                strokeWidth={2}
                strokeDasharray="3 3"
                label={{
                  value: `Call Wall: $${callWall.toFixed(0)}`,
                  position: 'top',
                  fill: '#10b981',
                  fontSize: 11,
                  fontWeight: 'bold',
                  offset: 20
                }}
              />
            )}

            {/* Put wall reference line (red, dotted) - matching Plotly */}
            {putWall && putWall > 0 && (
              <ReferenceLine
                x={putWall}
                stroke="#ef4444"
                strokeWidth={2}
                strokeDasharray="3 3"
                label={{
                  value: `Put Wall: $${putWall.toFixed(0)}`,
                  position: 'top',
                  fill: '#ef4444',
                  fontSize: 11,
                  fontWeight: 'bold',
                  offset: 30
                }}
              />
            )}

            {/* Net gamma bar (blue like Plotly) */}
            <Bar
              dataKey="totalGamma"
              name="Net Gamma"
              fill="#3b82f6"
              opacity={0.8}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
