'use client'

import Link from 'next/link'
import type { BriefRow } from '@/lib/forgeBriefings/types'
import BriefingMacroRibbon from './BriefingMacroRibbon'
import BriefingFactors from './BriefingFactors'
import BriefingTradeOfDay from './BriefingTradeOfDay'
import BriefingSparkline from './BriefingSparkline'
import BriefingWisdom from './BriefingWisdom'
import BriefingMoodGlyph from './BriefingMoodGlyph'

const BOT_ACCENT: Record<string, string> = {
  flame: 'text-amber-400', spark: 'text-blue-400', inferno: 'text-red-400', portfolio: 'text-amber-300',
}

export default function BriefingCard({ brief, compact = false }: { brief: BriefRow; compact?: boolean }) {
  const accent = BOT_ACCENT[brief.bot] || 'text-amber-300'

  if (compact) {
    return (
      <Link href={`/briefings/${encodeURIComponent(brief.brief_id)}`} className="block bg-forge-card rounded-lg p-4 hover:bg-forge-card/80 transition-colors">
        <div className="flex items-center justify-between mb-1">
          <span className={`uppercase font-medium ${accent} text-sm`}>{brief.bot}</span>
          <span className="text-xs text-gray-500">{String(brief.brief_date)}</span>
        </div>
        <div className="flex items-center gap-3">
          <div className={accent}><BriefingMoodGlyph mood={brief.mood} size={24} /></div>
          <div className="flex-1 min-w-0">
            <div className="text-sm text-gray-200 font-medium truncate">{brief.title}</div>
            <div className="text-xs text-gray-500 italic truncate">{brief.bot_voice_signature}</div>
          </div>
          <span className="text-xs text-gray-400">{brief.risk_score ?? '—'}/10</span>
        </div>
      </Link>
    )
  }

  return (
    <article className="space-y-5 briefing-fade-in">
      <BriefingMacroRibbon data={brief.macro_ribbon} />
      <div className={`text-lg italic ${accent}`} style={{ fontFamily: 'Georgia, serif' }}>
        {brief.bot_voice_signature}
      </div>
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">{brief.title}</h1>
        <div className="flex items-center gap-4 text-sm text-gray-400">
          <span className={`uppercase ${accent}`}>{brief.bot}</span>
          <span>·</span>
          <span>Risk {brief.risk_score ?? '—'}/10</span>
          <span>·</span>
          <span>Mood: {brief.mood ?? '—'}</span>
          <span className={accent}><BriefingMoodGlyph mood={brief.mood} size={20} /></span>
        </div>
      </div>
      <BriefingWisdom wisdom={brief.wisdom} />
      <div className="text-gray-200 leading-relaxed whitespace-pre-line">{brief.summary}</div>
      <div className="grid md:grid-cols-2 gap-4">
        <BriefingTradeOfDay trade={brief.trade_of_day} />
        <BriefingFactors factors={brief.factors} />
      </div>
      <div className="pt-4 border-t border-gray-800 space-y-3">
        <div>
          <div className="text-amber-300 text-xs uppercase tracking-wider mb-1">7-Day Equity</div>
          <BriefingSparkline data={brief.sparkline_data} />
        </div>
        <div className="flex justify-end gap-3">
          <a href={`/api/briefings/${encodeURIComponent(brief.brief_id)}/png`} download className="text-amber-400 hover:text-amber-300 text-sm">
            Download PNG
          </a>
          <Link href={`/calendar?date=${String(brief.brief_date)}`} className="text-gray-400 hover:text-gray-200 text-sm">
            Open in calendar →
          </Link>
        </div>
      </div>
    </article>
  )
}
