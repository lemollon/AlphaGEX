'use client'

import dynamic from 'next/dynamic'

const AccountsContent = dynamic(() => import('@/components/AccountsContent'), {
  ssr: false,
  loading: () => (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-white">Accounts</h1>
      <div className="animate-pulse space-y-3">
        <div className="h-20 bg-forge-card rounded-lg" />
        <div className="h-20 bg-forge-card rounded-lg" />
        <div className="h-20 bg-forge-card rounded-lg" />
      </div>
    </div>
  ),
})

export default function AccountsPage() {
  return <AccountsContent />
}
