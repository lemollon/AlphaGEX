'use client'

import dynamic from 'next/dynamic'

const CompareContent = dynamic(() => import('@/components/CompareContent'), {
  ssr: false,
  loading: () => (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 bg-forge-border/30 rounded w-64" />
      <div className="h-96 bg-forge-border/30 rounded-xl" />
      <div className="grid md:grid-cols-2 gap-6">
        <div className="h-48 bg-forge-border/30 rounded-xl" />
        <div className="h-48 bg-forge-border/30 rounded-xl" />
      </div>
    </div>
  ),
})

export default function ComparePage() {
  return <CompareContent />
}
