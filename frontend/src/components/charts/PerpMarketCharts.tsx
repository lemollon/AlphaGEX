'use client'

import dynamic from 'next/dynamic'

const PerpMarketCharts = dynamic(
  () => import('./PerpMarketChartsImpl'),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-[#0a0a0a] border border-gray-800 rounded-lg p-6 animate-pulse">
            <div className="h-6 bg-gray-800 rounded w-1/3 mb-4" />
            <div className="h-72 bg-gray-800/50 rounded" />
          </div>
        ))}
      </div>
    ),
  }
)

export default PerpMarketCharts
