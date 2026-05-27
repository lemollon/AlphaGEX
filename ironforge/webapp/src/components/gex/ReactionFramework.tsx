'use client'
import type { GexAnalysisData } from '@/lib/gex/types'
import { buildReactionFramework } from '@/lib/gex/derive'

export default function ReactionFramework({
  data, balanceLabel,
}: { data: GexAnalysisData; balanceLabel: string }) {
  const fw = buildReactionFramework({
    gammaForm: data.header.gamma_form,
    price: data.header.price,
    flip: data.header.gex_flip,
    callWall: data.levels.call_wall,
    putWall: data.levels.put_wall,
    balanceLabel,
  })
  return (
    <div className="bg-forge-card border border-forge-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">Reaction Framework</h3>
      <div className="mb-3">
        <div className="text-[11px] uppercase tracking-wide text-amber-300">Base Case</div>
        <p className="text-sm text-gray-200 mt-1">{fw.baseCase}</p>
      </div>
      <div className="mb-3">
        <div className="text-[11px] uppercase tracking-wide text-gray-500">Invalidated if</div>
        <p className="text-sm text-gray-300 mt-1">{fw.invalidatedIf}</p>
      </div>
      {fw.notes.length > 0 && (
        <ul className="space-y-1">
          {fw.notes.map((n, i) => (
            <li key={i} className="text-xs text-gray-400">{'•'} {n}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
