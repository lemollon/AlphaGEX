'use client'

import { BarChart3 } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { EquityCurvePoint, formatCurrency } from './types'

interface EquityCurveProps {
  equityCurve: EquityCurvePoint[]
  chartPeriod: 7 | 30 | 90
  onPeriodChange: (period: 7 | 30 | 90) => void
  startingCapital: number
}

export default function EquityCurve({ equityCurve, chartPeriod, onPeriodChange, startingCapital }: EquityCurveProps) {
  // Calculate min/max for chart
  const equityValues = equityCurve.map(p => p.equity)
  const minEquity = equityValues.length > 0 ? Math.min(...equityValues) : startingCapital
  const maxEquity = equityValues.length > 0 ? Math.max(...equityValues) : startingCapital
  const chartPadding = (maxEquity - minEquity) * 0.1 || startingCapital * 0.02

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <BarChart3 className="w-6 h-6 text-primary" />
          <h2 className="text-xl font-semibold text-text-primary">Equity Curve</h2>
        </div>
        <div className="flex gap-2">
          {[7, 30, 90].map((period) => (
            <button
              key={period}
              onClick={() => onPeriodChange(period as 7 | 30 | 90)}
              className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                chartPeriod === period
                  ? 'bg-primary text-white'
                  : 'bg-background-hover text-text-secondary hover:bg-background-primary'
              }`}
            >
              {period}D
            </button>
          ))}
        </div>
      </div>

      <div className="h-64">
        {equityCurve.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={equityCurve} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis
                dataKey="date"
                tick={{ fill: '#888', fontSize: 11 }}
                axisLine={{ stroke: '#444' }}
                tickLine={{ stroke: '#444' }}
              />
              <YAxis
                domain={[minEquity - chartPadding, maxEquity + chartPadding]}
                tick={{ fill: '#888', fontSize: 11 }}
                axisLine={{ stroke: '#444' }}
                tickLine={{ stroke: '#444' }}
                tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1a1a2e',
                  border: '1px solid #333',
                  borderRadius: '8px',
                  color: '#fff'
                }}
                formatter={(value: number) => [formatCurrency(value), 'Equity']}
                labelFormatter={(label) => `Date: ${label}`}
              />
              <ReferenceLine
                y={startingCapital}
                stroke="#666"
                strokeDasharray="5 5"
                label={{ value: 'Starting', fill: '#666', fontSize: 10 }}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#equityGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-text-secondary">
            <div className="text-center">
              <BarChart3 className="w-12 h-12 text-text-muted mx-auto mb-2" />
              <p>No equity data available yet</p>
              <p className="text-xs text-text-muted mt-1">Chart will populate as trades are executed</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
