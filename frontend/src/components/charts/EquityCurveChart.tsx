'use client'

import dynamic from 'next/dynamic'

const EquityCurveChart = dynamic(
  () => import('./EquityCurveChartImpl'),
  {
    ssr: false,
    loading: () => (
      <div className="bg-[#0a0a0a] border border-gray-800 rounded-lg p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-800 rounded w-1/3" />
          <div className="h-64 bg-gray-800/50 rounded" />
        </div>
      </div>
    ),
  }
)

export default EquityCurveChart
