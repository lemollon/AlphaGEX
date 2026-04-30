/**
 * Manual brief trigger.
 *
 *   GET  /api/{bot}/briefs/generate?type=morning|intraday|eod_debrief
 *     Dry-run preview: gathers inputs, builds the prompt, returns what
 *     would be sent to Claude (and the pending parse format). Does NOT
 *     call the API and does NOT store anything.
 *
 *   POST /api/{bot}/briefs/generate?type=morning|intraday|eod_debrief
 *     Real run: calls Claude with the gathered inputs, parses the
 *     response, stores into {bot}_market_briefs, returns the brief.
 *     Costs ~$0.02-0.05 per call depending on prompt size.
 */
import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import { generateBrief, gatherInputs, type BriefType } from '@/lib/market-brief'

export const dynamic = 'force-dynamic'

function parseBriefType(raw: string | null): BriefType | null {
  if (raw === 'morning' || raw === 'intraday' || raw === 'eod_debrief') return raw
  return null
}

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const briefType = parseBriefType(req.nextUrl.searchParams.get('type')) ?? 'intraday'

  try {
    const inputs = await gatherInputs(bot, briefType)
    return NextResponse.json({
      dry_run: true,
      bot,
      brief_type: briefType,
      inputs,
      note: 'POST to this same URL to actually call Claude and store the brief.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  const briefType = parseBriefType(req.nextUrl.searchParams.get('type')) ?? 'intraday'

  try {
    const result = await generateBrief(bot, briefType)
    return NextResponse.json({
      id: result.id,
      bot,
      brief_type: briefType,
      model: result.model,
      brief: result.brief,
      note: `Stored in ${bot}_market_briefs. View via GET /api/${bot}/briefs or /api/${bot}/briefs/latest.`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // Distinguish config errors from upstream failures
    const status = /CLAUDE_API_KEY/.test(msg) ? 500 : 502
    return NextResponse.json({ error: msg }, { status })
  }
}
