'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { useState } from 'react'
import { fetcher } from '@/lib/fetcher'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingCard from '@/components/BriefingCard'

export default function BriefingsArchive() {
  const [bot, setBot] = useState<string>('')
  const [type, setType] = useState<string>('')
  const [page, setPage] = useState(0)
  const PAGE = 20
  const url = `/api/briefings?limit=${PAGE}&offset=${page * PAGE}` +
    (bot ? `&bot=${bot}` : '') + (type ? `&type=${type}` : '')
  const { data } = useSWR<{ briefs: BriefRow[] }>(url, fetcher)
  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Briefings Archive</h1>
        <Link href="/briefings" className="text-sm text-gray-400 hover:text-gray-200">← Back</Link>
      </div>
      <div className="flex gap-3 text-sm">
        <select value={bot} onChange={e => { setBot(e.target.value); setPage(0) }} className="bg-forge-card border border-gray-700 rounded px-2 py-1 text-white">
          <option value="">All bots</option>
          <option value="flame">FLAME</option><option value="spark">SPARK</option>
          <option value="inferno">INFERNO</option><option value="portfolio">Portfolio</option>
        </select>
        <select value={type} onChange={e => { setType(e.target.value); setPage(0) }} className="bg-forge-card border border-gray-700 rounded px-2 py-1 text-white">
          <option value="">All types</option>
          <option value="daily_eod">Daily EOD</option>
          <option value="weekly_synth">Weekly</option>
          <option value="fomc_eve">FOMC eve</option>
          <option value="post_event">Post-event</option>
          <option value="codex_monthly">Codex</option>
        </select>
      </div>
      <div className="space-y-3">
        {(data?.briefs || []).map(b => <BriefingCard key={b.brief_id} brief={b} compact />)}
        {(!data?.briefs || data.briefs.length === 0) && (
          <div className="text-gray-500 text-sm py-8 text-center">No briefings match.</div>
        )}
      </div>
      <div className="flex justify-between">
        <button disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))} className="text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30">← Newer</button>
        <span className="text-xs text-gray-500">Page {page + 1}</span>
        <button disabled={!data?.briefs || data.briefs.length < PAGE} onClick={() => setPage(p => p + 1)} className="text-sm text-gray-400 hover:text-gray-200 disabled:opacity-30">Older →</button>
      </div>
    </div>
  )
}
