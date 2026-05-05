import { ImageResponse } from 'next/og'
import type { BriefRow } from './types'

export function renderBriefImage(brief: BriefRow): Response {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
          backgroundColor: '#0b0b0d', color: '#e5e7eb', padding: 64,
          fontFamily: 'serif',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: 28, color: '#fbbf24', letterSpacing: 2 }}>
            IRON · FORGE
          </div>
          <div style={{ fontSize: 22, color: '#9ca3af' }}>
            {String(brief.brief_date)} · {brief.bot.toUpperCase()}
          </div>
        </div>
        <div style={{ fontSize: 22, color: '#fbbf24', fontStyle: 'italic', marginBottom: 18 }}>
          {brief.bot_voice_signature || ''}
        </div>
        <div style={{ fontSize: 56, fontWeight: 700, lineHeight: 1.1, marginBottom: 28 }}>
          {brief.title}
        </div>
        {brief.wisdom ? (
          <div style={{
            fontSize: 30, fontStyle: 'italic', color: '#fbbf24', borderLeft: '4px solid #fbbf24',
            paddingLeft: 20, marginBottom: 28, lineHeight: 1.3,
          }}>
            "{brief.wisdom}"
          </div>
        ) : null}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 'auto', fontSize: 22 }}>
          <div style={{ color: '#9ca3af' }}>Risk {brief.risk_score ?? '—'}/10 · Mood {brief.mood ?? '—'}</div>
          <div style={{ color: '#9ca3af' }}>ironforge-899p.onrender.com</div>
        </div>
      </div>
    ),
    { width: 1200, height: 630 },
  )
}
