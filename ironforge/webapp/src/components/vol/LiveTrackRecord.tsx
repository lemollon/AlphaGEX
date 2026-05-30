'use client'

import {
  liveHeadline,
  resultMark,
  stanceLabel,
  fmtPct,
  type AdvisorLiveRecord,
  type AdvisorHistoryRow,
} from '@/lib/volatility'

const LABEL = 'text-[10px] text-forge-muted uppercase tracking-wider'

function resultClass(correct?: boolean | null): string {
  if (correct === true) return 'text-emerald-400'
  if (correct === false) return 'text-red-400'
  return 'text-forge-muted'
}

export default function LiveTrackRecord({
  record,
  rows,
}: {
  record?: AdvisorLiveRecord
  rows?: AdvisorHistoryRow[]
}) {
  const recent = (rows ?? []).slice(0, 20)

  return (
    <section className="rounded-xl border border-forge-border bg-forge-card/80 p-4">
      <div className={`${LABEL} mb-1`}>Live track record</div>
      <p className="mb-3 text-sm text-white">{liveHeadline(record)}</p>

      {recent.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-forge-muted">
                <th className="py-1 pr-3 font-normal">Date</th>
                <th className="py-1 pr-3 font-normal">Stance</th>
                <th className="py-1 pr-3 text-right font-normal">SPY 5d</th>
                <th className="py-1 pr-3 text-center font-normal">Result</th>
                <th className="py-1 text-center font-normal">In-window</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {recent.map((r, i) => {
                const spy =
                  r.realized_spy_ret === null || r.realized_spy_ret === undefined
                    ? '—'
                    : fmtPct(r.realized_spy_ret * 100)
                return (
                  <tr
                    key={`${r.log_date}-${i}`}
                    className="border-t border-forge-border/60"
                  >
                    <td className="py-1.5 pr-3 text-forge-muted">{r.log_date}</td>
                    <td className="py-1.5 pr-3 font-sans text-white">
                      {stanceLabel(r.stance)}
                    </td>
                    <td
                      className={`py-1.5 pr-3 text-right ${
                        spy.startsWith('+')
                          ? 'text-emerald-400'
                          : spy.startsWith('-')
                            ? 'text-red-400'
                            : 'text-forge-muted'
                      }`}
                    >
                      {spy}
                    </td>
                    <td
                      className={`py-1.5 pr-3 text-center ${resultClass(r.correct)}`}
                    >
                      {resultMark(r.correct)}
                    </td>
                    <td className="py-1.5 text-center text-forge-muted">
                      {r.in_window === true
                        ? '✓'
                        : r.in_window === false
                          ? '✗'
                          : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
