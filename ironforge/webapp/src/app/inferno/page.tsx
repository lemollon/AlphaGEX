'use client'

import dynamic from 'next/dynamic'

const BotDashboard = dynamic(() => import('@/components/BotDashboard'), {
  ssr: false,
  loading: () => (
    <div className="space-y-6 animate-pulse">
      <div className="h-8 bg-forge-border/30 rounded w-40" />
      <div className="h-48 bg-forge-border/30 rounded-xl" />
      <div className="h-32 bg-forge-border/30 rounded-xl" />
    </div>
  ),
})

export default function InfernoPage() {
  return <BotDashboard bot="inferno" accent="red" />
}
