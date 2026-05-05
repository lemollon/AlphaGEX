'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'

export default function BriefingsCodex() {
  const { data } = useSWR<{ briefs: BriefRow[] }>('/api/briefings?type=codex_monthly&limit=100', fetcher)
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Forge Codex</h1>
        <Link href="/briefings" className="text-sm text-gray-400 hover:text-gray-200">← Back</Link>
      </div>
      <p className="text-gray-400 text-sm">Monthly long-memory entries — distilled themes a future-you should remember.</p>
      <div className="space-y-3">
        {(data?.briefs || []).map(b => (
          <details key={b.brief_id} className="bg-forge-card rounded-lg p-4">
            <summary className="cursor-pointer flex items-baseline justify-between">
              <span className="text-amber-300 font-medium">{String(b.brief_date).slice(0, 7)} · {b.bot}</span>
              <span className="text-sm text-gray-400">{b.title}</span>
            </summary>
            <div className="mt-3 text-gray-200 whitespace-pre-line text-sm">{b.summary}</div>
            <div className="mt-3 text-xs">
              <Link href={`/briefings/${encodeURIComponent(b.brief_id)}`} className="text-amber-400 hover:text-amber-300">Open full →</Link>
            </div>
          </details>
        ))}
        {(!data?.briefs || data.briefs.length === 0) && (
          <div className="text-gray-500 text-sm py-8 text-center">No codex entries yet.</div>
        )}
      </div>
    </div>
  )
}
