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

/* EMERGENCY CLOSE ALL. The component and POST /api/sandbox/emergency-close were
 * both fully built, but the panel was mounted on NO page — the panic button could
 * not be reached from anywhere in the console. /accounts is where the broker
 * accounts it acts on are already listed. */
const SandboxKillSwitch = dynamic(() => import('@/components/SandboxKillSwitch'), { ssr: false })

export default function AccountsPage() {
  return (
    <div className="space-y-6">
      <AccountsContent />
      <SandboxKillSwitch />
    </div>
  )
}
