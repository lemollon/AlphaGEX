'use client'

import dynamic from 'next/dynamic'

const VolatilityComparisonContent = dynamic(() => import('./VolatilityComparisonContent'), {
  ssr: false,
  loading: () => (
    <div className="min-h-screen bg-[#030712]">
      <div className="animate-pulse p-8 space-y-6">
        <div className="h-10 bg-gray-800 rounded w-1/3" />
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-800/50 rounded-lg" />
          ))}
        </div>
        <div className="h-96 bg-gray-800/30 rounded-lg" />
      </div>
    </div>
  ),
})

export default function VolatilityComparisonPage() {
  return <VolatilityComparisonContent />
}
