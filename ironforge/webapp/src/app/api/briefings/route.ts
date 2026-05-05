import { NextRequest, NextResponse } from 'next/server'
import { listInRange } from '@/lib/forgeBriefings/repo'
import type { BotKey, BriefType } from '@/lib/forgeBriefings/types'

export const dynamic = 'force-dynamic'

const BOTS = new Set<BotKey>(['flame', 'spark', 'inferno', 'portfolio'])
const TYPES = new Set<BriefType>(['daily_eod', 'fomc_eve', 'post_event', 'weekly_synth', 'codex_monthly'])

export async function GET(req: NextRequest) {
  const sp = new URL(req.url).searchParams
  const opts: any = {
    from: sp.get('from') || undefined,
    to: sp.get('to') || undefined,
    limit: sp.get('limit') ? parseInt(sp.get('limit')!) : undefined,
    offset: sp.get('offset') ? parseInt(sp.get('offset')!) : undefined,
  }
  const bot = sp.get('bot') as BotKey | null
  const type = sp.get('type') as BriefType | null
  if (bot && BOTS.has(bot)) opts.bot = bot
  if (type && TYPES.has(type)) opts.brief_type = type
  try {
    const briefs = await listInRange(opts)
    return NextResponse.json({ briefs })
  } catch (err) {
    return NextResponse.json({ error: (err as Error).message }, { status: 500 })
  }
}
