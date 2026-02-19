'use client'

import dynamic from 'next/dynamic'

// Jubilee is 4,457 lines with recharts + 23 useSWR hooks.
// Defer the entire page content so the initial shell loads instantly
// and recharts (~110KB) is fetched asynchronously.
const JubileeContent = dynamic(() => import('./JubileeContent'), {
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

export default function JubileePage() {
  return <JubileeContent />
}
