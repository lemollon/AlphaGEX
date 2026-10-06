/**
 * Agent lead tile (dev-handoff §6, gap-audit "MISSING: Agent lead tile"):
 * "Days the trade kept its credit: X of Y" — winning trading days over total
 * trading days the agent has actually traded. Null `lead` (no closed trade
 * yet) renders nothing — an honest empty state, not a fabricated 0 of 0.
 */
export default function AgentLeadTile({
  label,
  lead,
  accentClass = 'text-[var(--accent-text)]',
}: {
  label: string
  lead: { kept: number; total: number } | null
  accentClass?: string
}) {
  if (!lead || lead.total === 0) return null
  const pct = Math.round((lead.kept / lead.total) * 100)
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--bg)]/80 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{label} — Days Kept Credit</div>
      <div className="mt-1.5 flex items-baseline gap-2">
        <span className={`font-mono text-2xl font-bold ${accentClass}`}>{lead.kept} of {lead.total}</span>
        <span className="text-xs text-[var(--muted)]">{pct}% of trading days</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-forge-border">
        <div className={`h-full rounded-full ${lead.kept / lead.total >= 0.5 ? 'bg-[var(--up)]' : 'bg-[var(--bad)]'}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
