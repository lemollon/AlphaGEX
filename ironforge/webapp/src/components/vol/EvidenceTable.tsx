'use client'

import { evidenceRows, type AdvisorEvidence } from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

function pctClass(v: string): string {
  if (v.startsWith('+')) return 'text-emerald-400'
  if (v.startsWith('-')) return 'text-red-400'
  return 'text-white'
}

export default function EvidenceTable({
  evidence,
}: {
  evidence?: AdvisorEvidence
}) {
  const rows = evidenceRows(evidence)

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className={`${LABEL} mb-3`}>Evidence (2006–present)</div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-forge-muted">
              <th className="py-1 pr-3 font-normal">Signal</th>
              <th className="py-1 pr-3 text-right font-normal">N</th>
              <th className="py-1 pr-3 text-right font-normal">Hit rate</th>
              <th className="py-1 pr-3 text-right font-normal">Fwd VIX 5d</th>
              <th className="py-1 pr-3 text-right font-normal">Fwd SPY 5d</th>
              <th className="py-1 text-right font-normal">Median timing</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-forge-border/60">
                <td className="py-1.5 pr-3 font-sans text-white">{r.name}</td>
                <td className="py-1.5 pr-3 text-right text-forge-muted">{r.n}</td>
                <td className="py-1.5 pr-3 text-right text-white">{r.hitRate}</td>
                <td className={`py-1.5 pr-3 text-right ${pctClass(r.fwdVix5)}`}>
                  {r.fwdVix5}
                </td>
                <td className={`py-1.5 pr-3 text-right ${pctClass(r.fwdSpy5)}`}>
                  {r.fwdSpy5}
                </td>
                <td className="py-1.5 text-right text-forge-muted">{r.timing}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-forge-muted">
        VVIX divergence is shown for completeness but is statistically
        insignificant.
      </p>
    </section>
  )
}
