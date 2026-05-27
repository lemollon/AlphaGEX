'use client'
import type { StructureBalance } from '@/lib/gex/types'

export default function StructureBalanceCard({
  sb, loading,
}: { sb?: StructureBalance; loading?: boolean }) {
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-2">
        Structure Balance <span className="text-xs text-gray-500">(7-Day Horizon)</span>
      </h3>
      {loading ? (
        <p className="text-xs text-gray-500">Loading full board…</p>
      ) : !sb ? (
        <p className="text-xs text-gray-500">Not available.</p>
      ) : (
        <>
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold text-amber-300">{sb.label}</span>
            <span className="text-sm text-gray-400">{sb.balance.toFixed(3)}</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">{sb.summary}</p>
        </>
      )}
    </div>
  )
}
