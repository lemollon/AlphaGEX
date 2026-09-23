'use client'

import dynamic from 'next/dynamic'
import { Suspense } from 'react'

const AgapePerpsContent = dynamic(() => import('./AgapePerpsContent'), {
  ssr: false,
  loading: () => <div className="min-h-screen bg-[#0a0e1a]" />,
})

export default function AgapePerpsPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-[#0a0e1a]" />}>
      <AgapePerpsContent />
    </Suspense>
  )
}
