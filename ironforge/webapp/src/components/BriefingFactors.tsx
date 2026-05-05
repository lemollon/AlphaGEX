import type { Factor } from '@/lib/forgeBriefings/types'

export default function BriefingFactors({ factors }: { factors: Factor[] | null }) {
  if (!factors || factors.length === 0) return null
  return (
    <div className="bg-forge-card rounded-lg p-4">
      <h3 className="text-amber-300 text-sm uppercase tracking-wider mb-3">Factors</h3>
      <ol className="space-y-3">
        {factors.map(f => (
          <li key={f.rank} className="text-sm text-gray-200">
            <span className="text-amber-400 font-medium mr-2">{f.rank}.</span>
            <span className="font-medium">{f.title}</span>
            <p className="text-gray-400 text-xs mt-0.5 ml-5">{f.detail}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
