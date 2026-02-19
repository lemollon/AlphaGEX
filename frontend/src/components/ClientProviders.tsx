'use client'

import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { SWRConfig } from 'swr'
import { ToastProvider } from './ui/Toast'
import { swrConfig, prefetchMarketData } from '@/lib/hooks/useMarketData'
import { SidebarProvider } from '@/contexts/SidebarContext'

// Lazy-load the chatbot — it's 1,153 lines + react-markdown and most users
// don't interact with it on every page load. Defers ~50KB from First Load JS.
const FloatingChatbot = dynamic(() => import('./FloatingChatbot'), {
  ssr: false,
})

interface ClientProvidersProps {
  children: React.ReactNode
}

export default function ClientProviders({ children }: ClientProvidersProps) {
  // Prefetch common data when app loads
  useEffect(() => {
    // Small delay to let the app render first
    const timer = setTimeout(() => {
      prefetchMarketData.all('SPY')
    }, 100)

    return () => clearTimeout(timer)
  }, [])

  return (
    <SWRConfig value={swrConfig}>
      <SidebarProvider>
        <ToastProvider>
          {children}
          <FloatingChatbot />
        </ToastProvider>
      </SidebarProvider>
    </SWRConfig>
  )
}
