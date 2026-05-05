'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import WeeklySynthesisHero from '@/components/WeeklySynthesisHero'
import BriefingCard from '@/components/BriefingCard'

export default function BriefingsHub() {
  const { data: dailies } = useSWR<{ briefs: BriefRow[] }>('/api/briefings?type=daily_eod&limit=12', fetcher, { refreshInterval: 60_000 })
  const { data: codex } = useSWR<{ briefs: BriefRow[] }>('/api/briefings?type=codex_monthly&limit=3', fetcher)

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Briefings</h1>
        <div className="flex gap-4 text-sm">
          <Link href="/briefings/archive" className="text-gray-400 hover:text-gray-200">Archive</Link>
          <Link href="/briefings/codex" className="text-gray-400 hover:text-gray-200">Codex</Link>
        </div>
      </div>

      <WeeklySynthesisHero />

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-3">
          <h2 className="text-amber-300 text-sm uppercase tracking-wider">Recent Daily Reports</h2>
          {(dailies?.briefs || []).map(b => (
            <BriefingCard key={b.brief_id} brief={b} compact />
          ))}
          {(!dailies?.briefs || dailies.briefs.length === 0) && (
            <div className="text-gray-500 text-sm py-8 text-center">No daily briefings yet.</div>
          )}
        </div>

        <aside className="space-y-3">
          <h2 className="text-amber-300 text-sm uppercase tracking-wider">Forge Codex</h2>
          {(codex?.briefs || []).map(b => (
            <Link key={b.brief_id} href={`/briefings/${encodeURIComponent(b.brief_id)}`} className="block bg-forge-card rounded-lg p-4 hover:bg-forge-card/80">
              <div className="text-xs text-gray-500 mb-1">{String(b.brief_date).slice(0, 7)} · {b.bot}</div>
              <div className="text-sm text-gray-200 font-medium">{b.title}</div>
            </Link>
          ))}
          {(!codex?.briefs || codex.briefs.length === 0) && (
            <div className="text-gray-500 text-xs italic py-4">First codex entry posts at month-end.</div>
          )}
          <Link href="/briefings/codex" className="block text-center text-sm text-amber-400 hover:text-amber-300 py-2">
            Browse all codex →
          </Link>
        </aside>
      </div>
    </div>
  )
}
