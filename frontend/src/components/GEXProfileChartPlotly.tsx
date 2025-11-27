'use client'

import dynamic from 'next/dynamic'
import { useMemo } from 'react'

// Dynamically import Plotly to avoid SSR issues
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

interface GEXLevel {
  strike: number
  call_gex: number
  put_gex: number
  total_gex: number
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

  // Calculate stats (guard against empty arrays returning -Infinity)
  const maxCallGamma = data.length > 0 ? Math.max(...data.map(d => Math.abs(d.call_gex))) / 1e6 : 0
  const maxPutGamma = data.length > 0 ? Math.max(...data.map(d => Math.abs(d.put_gex))) / 1e6 : 0

  // Prepare chart data - separate Call and Put GEX
  const chartData = useMemo(() => {
    const strikes = data.map(d => d.strike)
    // Call GEX: Always positive, displays ABOVE axis (green bars on top)
    const callGamma = data.map(d => Math.abs(d.call_gex) / 1e6)
    // Put GEX: Always negative, displays BELOW axis (red bars on bottom)
    const putGamma = data.map(d => -Math.abs(d.put_gex) / 1e6)

    return {
      strikes,
      callGamma,
      putGamma
    }
  }, [data])

  // Create annotations (labels)
  const annotations = useMemo(() => {
    const annots: any[] = []
    const maxValue = Math.max(
      ...chartData.callGamma.map(Math.abs),
      ...chartData.putGamma.map(Math.abs)
    )

    // Spot Price
    if (spotPrice && spotPrice > 0) {
      annots.push({
        x: spotPrice,
        y: maxValue * 1.15,
        text: `📍 SPOT: $${spotPrice.toFixed(2)}`,
        showarrow: false,
        font: { color: '#fbbf24', size: 12, family: 'Arial, sans-serif' },
        bgcolor: 'rgba(0,0,0,0.8)',
        bordercolor: '#fbbf24',
        borderwidth: 2,
        borderpad: 4,
        xanchor: 'center',
        yanchor: 'bottom'
      })
    }

    // Flip Point
    if (flipPoint && flipPoint > 0) {
      annots.push({
        x: flipPoint,
        y: maxValue * 1.05,
        text: `⚡ FLIP: $${flipPoint.toFixed(2)}`,
        showarrow: false,
        font: { color: '#fb923c', size: 12, family: 'Arial, sans-serif' },
        bgcolor: 'rgba(0,0,0,0.8)',
        bordercolor: '#fb923c',
        borderwidth: 2,
        borderpad: 4,
        xanchor: 'center',
        yanchor: 'bottom'
      })
    }

    // Call Wall
    if (callWall && callWall > 0) {
      annots.push({
        x: callWall,
        y: maxValue * 0.95,
        text: `🔴 CALL: $${callWall.toFixed(2)}`,
        showarrow: false,
        font: { color: '#10b981', size: 12, family: 'Arial, sans-serif' },
        bgcolor: 'rgba(0,0,0,0.8)',
        bordercolor: '#10b981',
        borderwidth: 2,
        borderpad: 4,
        xanchor: 'center',
        yanchor: 'bottom'
      })
    }

    // Put Wall
    if (putWall && putWall > 0) {
      annots.push({
        x: putWall,
        y: maxValue * 0.85,
        text: `🟢 PUT: $${putWall.toFixed(2)}`,
        showarrow: false,
        font: { color: '#ef4444', size: 12, family: 'Arial, sans-serif' },
        bgcolor: 'rgba(0,0,0,0.8)',
        bordercolor: '#ef4444',
        borderwidth: 2,
        borderpad: 4,
        xanchor: 'center',
        yanchor: 'bottom'
      })
    }

    return annots
  }, [spotPrice, flipPoint, callWall, putWall, chartData.callGamma, chartData.putGamma])

  // Create shapes (vertical lines)
  const shapes = useMemo(() => {
    const shapesList: any[] = []
    const allValues = [...chartData.callGamma, ...chartData.putGamma]
    const yMin = Math.min(...allValues) * 1.2
    const yMax = Math.max(...allValues) * 1.2

    if (spotPrice && spotPrice > 0) {
      shapesList.push({
        type: 'line',
        x0: spotPrice,
        x1: spotPrice,
        y0: yMin,
        y1: yMax,
        line: { color: '#fbbf24', width: 3, dash: 'dash' }
      })
    }

    if (flipPoint && flipPoint > 0) {
      shapesList.push({
        type: 'line',
        x0: flipPoint,
        x1: flipPoint,
        y0: yMin,
        y1: yMax,
        line: { color: '#fb923c', width: 3, dash: 'dash' }
      })
    }

    if (callWall && callWall > 0) {
      shapesList.push({
        type: 'line',
        x0: callWall,
        x1: callWall,
        y0: yMin,
        y1: yMax,
        line: { color: '#10b981', width: 3, dash: 'dot' }
      })
    }

    if (putWall && putWall > 0) {
      shapesList.push({
        type: 'line',
        x0: putWall,
        x1: putWall,
        y0: yMin,
        y1: yMax,
        line: { color: '#ef4444', width: 3, dash: 'dot' }
      })
    }

    return shapesList
  }, [spotPrice, flipPoint, callWall, putWall, chartData.callGamma, chartData.putGamma])

  return (
    <div className="w-full space-y-4">
      {/* Stats Bar */}
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
            {(chartData.callGamma.reduce((sum, v) => sum + v, 0) + chartData.putGamma.reduce((sum, v) => sum + v, 0)).toFixed(0)}M
          </p>
          <p className="text-xs text-text-muted mt-1">
            {(chartData.callGamma.reduce((sum, v) => sum + v, 0) + chartData.putGamma.reduce((sum, v) => sum + v, 0)) > 0 ? "Positive = Range bound" : "Negative = Volatile"}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="bg-background-deep rounded-lg p-4 border-2 border-primary/50">
        <div className="mb-4">
          <h3 className="text-lg font-bold text-text-primary">📊 Call & Put GEX Profile</h3>
          <p className="text-sm text-text-secondary mt-1">
            Green bars = Call GEX (resistance above) | Red bars = Put GEX (support below)
          </p>
        </div>

        <Plot
          data={[
            {
              x: chartData.strikes,
              y: chartData.callGamma,
              type: 'bar',
              marker: {
                color: '#10b981',
                line: { width: 0 }
              },
              name: 'Call GEX',
              hovertemplate: '<b>Strike: $%{x:.2f}</b><br>Call GEX: %{y:.1f}M<br><extra></extra>'
            },
            {
              x: chartData.strikes,
              y: chartData.putGamma,
              type: 'bar',
              marker: {
                color: '#ef4444',
                line: { width: 0 }
              },
              name: 'Put GEX',
              hovertemplate: '<b>Strike: $%{x:.2f}</b><br>Put GEX: %{y:.1f}M<br><extra></extra>'
            }
          ]}
          layout={{
            height: height,
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#9ca3af', family: 'Arial, sans-serif' },
            xaxis: {
              title: { text: 'Strike Price' },
              gridcolor: '#1a1f2e',
              tickformat: '$,.0f',
              showgrid: true
            },
            yaxis: {
              title: { text: 'Gamma Exposure ($M)' },
              gridcolor: '#1a1f2e',
              showgrid: true,
              zeroline: true,
              zerolinecolor: '#6b7280',
              zerolinewidth: 2
            },
            shapes: shapes,
            annotations: annotations,
            margin: { t: 100, b: 60, l: 60, r: 40 },
            hovermode: 'closest',
            showlegend: true,
            legend: {
              x: 1,
              y: 1,
              xanchor: 'right',
              bgcolor: 'rgba(0,0,0,0.8)',
              bordercolor: '#6b7280',
              borderwidth: 1,
              font: { color: '#9ca3af' }
            },
            barmode: 'relative'
          }}
          config={{
            displayModeBar: false,
            responsive: true
          }}
          style={{ width: '100%', height: '100%' }}
        />
      </div>

      {/* Actionable Legend */}
      <div className="bg-background-hover rounded-lg p-4 border border-border">
        <h4 className="font-bold text-text-primary mb-2">💰 How to Use This Chart:</h4>
        <ul className="space-y-1 text-sm text-text-secondary">
          <li>• <span className="text-success font-semibold">🔴 Call Wall</span> = Resistance - price gets rejected</li>
          <li>• <span className="text-danger font-semibold">🟢 Put Wall</span> = Support - price finds floor</li>
          <li>• <span className="text-warning font-semibold">⚡ Flip Point</span> = Regime change threshold</li>
          <li>• <span className="text-primary font-semibold">📍 Spot</span> = Current market price</li>
          <li>• Price tends to <span className="font-semibold">bounce between walls</span> - trade the range!</li>
        </ul>
      </div>
    </div>
  )
}
