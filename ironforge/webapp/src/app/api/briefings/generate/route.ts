import { NextRequest, NextResponse } from 'next/server'
import { generateBrief } from '@/lib/forgeBriefings/generate'
import type { BotKey, BriefType } from '@/lib/forgeBriefings/types'

export const dynamic = 'force-dynamic'

const BOTS = new Set<BotKey>(['flame', 'spark', 'inferno', 'portfolio'])
const TYPES = new Set<BriefType>(['daily_eod', 'fomc_eve', 'post_event', 'weekly_synth', 'codex_monthly'])

export async function POST(req: NextRequest) {
  const sp = new URL(req.url).searchParams
  const body = await req.json().catch(() => ({}))
  const bot = ((body.bot as BotKey) || (sp.get('bot') as BotKey) || 'portfolio')
  const brief_type = ((body.brief_type as BriefType) || (sp.get('type') as BriefType) || 'daily_eod')
  const force = body.force === true || sp.get('force') === '1'
  const brief_date = body.brief_date || sp.get('brief_date') ||
    new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' })

  if (!BOTS.has(bot) || !TYPES.has(brief_type)) {
    return NextResponse.json({ error: 'invalid bot or type' }, { status: 400 })
  }

  const baseUrl = req.nextUrl.origin
  try {
    const result = await generateBrief({ bot, brief_type, brief_date, baseUrl, force })
    return NextResponse.json(result)
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
