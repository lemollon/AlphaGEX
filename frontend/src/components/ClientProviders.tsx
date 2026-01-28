'use client'

import { useEffect } from 'react'
import { SWRConfig } from 'swr'
import FloatingChatbot from './FloatingChatbot'
import { ToastProvider } from './ui/Toast'
import { swrConfig, prefetchMarketData } from '@/lib/hooks/useMarketData'
import { SidebarProvider } from '@/contexts/SidebarContext'

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
