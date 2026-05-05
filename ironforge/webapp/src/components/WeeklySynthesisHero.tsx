'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingSparkline from './BriefingSparkline'

export default function WeeklySynthesisHero() {
  const { data } = useSWR<{ briefs: BriefRow[] }>(
    '/api/briefings?bot=portfolio&type=weekly_synth&limit=1',
    fetcher,
    { refreshInterval: 5 * 60 * 1000 },
  )
  const brief = data?.briefs?.[0]
  if (!brief) {
    return (
      <div className="rounded-lg border border-amber-900/40 bg-forge-card p-8 text-center text-gray-400">
        No weekly synthesis yet. Friday after close, the Master of the Forge will speak.
      </div>
    )
  }
  return (
    <Link href={`/briefings/${encodeURIComponent(brief.brief_id)}`}
          className="block rounded-lg border border-amber-700/40 bg-gradient-to-br from-forge-card to-forge-card/40 p-8 hover:border-amber-500/60 transition-colors briefing-fade-in">
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-xs uppercase tracking-widest text-amber-400">This Week in Iron</span>
        <span className="text-xs text-gray-500">Wk of {String(brief.brief_date)}</span>
      </div>
      <h2 className="text-3xl font-bold text-white mb-3">{brief.title}</h2>
      <p className="text-amber-300 italic mb-4" style={{ fontFamily: 'Georgia, serif' }}>
        {brief.bot_voice_signature}
      </p>
      <p className="text-gray-300 leading-relaxed line-clamp-4 mb-4">{brief.summary}</p>
      {brief.wisdom ? (
        <p className="text-amber-300 italic text-lg" style={{ fontFamily: 'Georgia, serif' }}>&ldquo;{brief.wisdom}&rdquo;</p>
      ) : null}
      <div className="mt-4 space-y-3">
        <div>
          <div className="text-amber-300 text-xs uppercase tracking-wider mb-1">7-Day Equity</div>
          <BriefingSparkline data={brief.sparkline_data} />
        </div>
        <div className="text-right">
          <span className="text-amber-400 text-sm">Read full →</span>
        </div>
      </div>
    </Link>
  )
}
