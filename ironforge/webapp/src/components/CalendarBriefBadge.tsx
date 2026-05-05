import type { Mood } from '@/lib/forgeBriefings/types'

const TINT: Record<Mood, string> = {
  forged: 'text-emerald-400', measured: 'text-amber-300',
  cooled: 'text-gray-400', burning: 'text-red-400',
}

export default function CalendarBriefBadge({ mood }: { mood: Mood | null | undefined }) {
  return (
    <span className={`absolute top-0 right-0 ${mood ? TINT[mood] : 'text-amber-300'}`}
          style={{ width: 10, height: 10 }}>
      <img src="/glyph-brief-badge.svg" alt="" style={{ width: 10, height: 10 }} />
    </span>
  )
}
