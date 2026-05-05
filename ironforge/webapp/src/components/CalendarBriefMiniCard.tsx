import type { Mood } from '@/lib/forgeBriefings/types'

interface DayBadge {
  brief_date: string
  per_bot: Record<string, { mood: Mood | null; risk_score: number | null; brief_id: string }>
  lead: { brief_id: string; risk_score: number | null; first_sentence: string } | null
}

const MOOD_DOT: Record<Mood, string> = {
  forged: 'bg-emerald-400', measured: 'bg-amber-300',
  cooled: 'bg-gray-400', burning: 'bg-red-400',
}

export default function CalendarBriefMiniCard({ day }: { day: DayBadge }) {
  return (
    <div className="absolute z-50 bg-forge-card border border-amber-900/60 rounded-lg p-3 shadow-xl text-xs text-gray-200 pointer-events-none"
         style={{ width: 220, marginTop: 4 }}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-amber-300">{day.brief_date}</span>
        {day.lead?.risk_score != null ? <span className="text-gray-400">Risk {day.lead.risk_score}/10</span> : null}
      </div>
      <div className="flex gap-1 mb-2">
        {(['flame','spark','inferno','portfolio'] as const).map(b => {
          const pb = day.per_bot[b]
          if (!pb) return null
          return (
            <span key={b} className={`inline-block w-2 h-2 rounded-full ${pb.mood ? MOOD_DOT[pb.mood] : 'bg-gray-600'}`} title={`${b}: ${pb.mood ?? '—'}`} />
          )
        })}
      </div>
      {day.lead?.first_sentence ? (
        <p className="text-gray-300 line-clamp-3 italic">{day.lead.first_sentence}</p>
      ) : null}
    </div>
  )
}
