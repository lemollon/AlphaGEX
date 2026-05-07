'use client'

import { usePathname } from 'next/navigation'
import ClientNav from './ClientNav'

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isLanding = pathname === '/'

  if (isLanding) {
    return <>{children}</>
  }

  return (
    <>
      <ClientNav />
      <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>
    </>
  )
}
