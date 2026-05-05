import type { Mood } from '@/lib/forgeBriefings/types'

const SRC: Record<Mood, string> = {
  forged:   '/glyph-mood-forged.svg',
  measured: '/glyph-mood-measured.svg',
  cooled:   '/glyph-mood-cooled.svg',
  burning:  '/glyph-mood-burning.svg',
}

export default function BriefingMoodGlyph({ mood, size = 32 }: { mood: Mood | null; bot?: string; size?: number }) {
  if (!mood) return null
  return (
    <span title={mood} style={{ display: 'inline-block', width: size, height: size }}>
      <img src={SRC[mood]} alt={mood} style={{ width: size, height: size, opacity: 0.85 }} />
    </span>
  )
}
