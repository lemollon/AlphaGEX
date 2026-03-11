'use client'

import dynamic from 'next/dynamic'

const Nav = dynamic(() => import('./Nav'), {
  ssr: false,
  loading: () => (
    <nav className="border-b border-amber-900/30 bg-forge-bg/95 backdrop-blur-sm">
      <div className="max-w-7xl mx-auto px-4 py-2 h-[36px]" />
    </nav>
  ),
})

export default function ClientNav() {
  return <Nav />
}
