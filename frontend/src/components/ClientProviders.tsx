'use client'

import FloatingChatbot from './FloatingChatbot'

interface ClientProvidersProps {
  children: React.ReactNode
}

export default function ClientProviders({ children }: ClientProvidersProps) {
  return (
    <>
      {children}
      <FloatingChatbot />
    </>
  )
}
