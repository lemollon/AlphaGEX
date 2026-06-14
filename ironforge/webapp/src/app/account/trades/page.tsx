import TradeApprovalsClient from './TradeApprovalsClient'

export const dynamic = 'force-dynamic'

export default function TradeApprovalsPage() {
  // Page shell is middleware-open; the data API (/api/brokerage/trades) enforces the customer
  // session and 401s when unauthenticated, which the client renders as a sign-in prompt.
  return (
    <div className="min-h-screen bg-forge-bg bg-ember-glow px-4 py-16">
      <div className="mx-auto max-w-md">
        <h1 className="mb-1 text-2xl font-bold text-white">Trades awaiting your approval</h1>
        <p className="mb-6 text-sm text-gray-400">
          IronForge never places a trade without your explicit approval. Review each one below.
        </p>
        <TradeApprovalsClient />
      </div>
    </div>
  )
}
