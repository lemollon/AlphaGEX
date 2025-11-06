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
  height?: number
}

export default function GEXProfileChart({
  data,
  spotPrice,
  height = 400
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

  // Transform data for chart - convert to millions for readability
  const chartData = data.map(level => ({
    strike: level.strike,
    strikeLabel: `$${level.strike.toFixed(0)}`,
    callGamma: (level.call_gex / 1_000_000), // Convert to millions
    putGamma: -(Math.abs(level.put_gex) / 1_000_000), // Negative for chart display
    netGamma: (level.total_gex / 1_000_000),
    isSpot: spotPrice && Math.abs(level.strike - spotPrice) < 1
  }))

  // Find min/max for Y-axis
  const allValues = chartData.flatMap(d => [d.callGamma, d.putGamma, d.netGamma])
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
    <div className="w-full space-y-4">
      {/* Call and Put Gamma (Stacked) */}
      <div className="bg-background-deep rounded-lg p-4 border border-border">
        <h3 className="text-sm font-semibold text-text-secondary mb-3">Gamma Exposure by Strike</h3>
        <ResponsiveContainer width="100%" height={height * 0.6}>
          <BarChart
            data={chartData}
            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
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
              label={{ value: 'Gamma ($M)', angle: -90, position: 'insideLeft', fill: '#9ca3af' }}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ paddingTop: '10px' }}
              iconType="square"
            />

            {/* Spot price reference line */}
            {spotPrice && (
              <ReferenceLine
                x={spotPrice}
                stroke="#fbbf24"
                strokeWidth={2}
                strokeDasharray="5 5"
                label={{ value: 'Spot', position: 'top', fill: '#fbbf24', fontSize: 12 }}
              />
            )}

            <Bar
              dataKey="callGamma"
              name="Call Gamma"
              fill="#10b981"
              opacity={0.8}
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="putGamma"
              name="Put Gamma"
              fill="#ef4444"
              opacity={0.8}
              radius={[0, 0, 4, 4]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Net Gamma Profile */}
      <div className="bg-background-deep rounded-lg p-4 border border-border">
        <h3 className="text-sm font-semibold text-text-secondary mb-3">Net Gamma Profile</h3>
        <ResponsiveContainer width="100%" height={height * 0.35}>
          <BarChart
            data={chartData}
            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
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

            {/* Spot price reference line */}
            {spotPrice && (
              <ReferenceLine
                x={spotPrice}
                stroke="#fbbf24"
                strokeWidth={2}
                strokeDasharray="5 5"
                label={{ value: 'Spot', position: 'top', fill: '#fbbf24', fontSize: 12 }}
              />
            )}

            <Bar
              dataKey="netGamma"
              name="Net Gamma"
              fill="#3b82f6"
              opacity={0.9}
              radius={[4, 4, 4, 4]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
