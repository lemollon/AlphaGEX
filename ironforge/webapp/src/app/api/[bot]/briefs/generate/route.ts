/**
 * Manual brief trigger (Q1). SPARK-only.
 *
 *   GET  /api/spark/briefs/generate?type=morning|intraday|eod_debrief
 *     Dry-run preview: gathers inputs, builds the prompt, returns what
 *     would be sent to Claude (and the pending parse format). Does NOT
 *     call the API and does NOT store anything. Free — useful for
 *     verifying input gathering + prompt rendering.
 *
 *   POST /api/spark/briefs/generate?type=morning|intraday|eod_debrief
 *     Real run: calls Claude with the gathered inputs, parses the
 *     response, stores into spark_market_briefs, returns the brief.
 *     Costs ~$0.02-0.05 per call depending on prompt size.
 *
 * Scheduler integration (Q2, not yet) will call generateBrief()
 * directly from scanner.ts — this route is for manual ops use.
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
  if (bot !== 'spark') {
    return NextResponse.json({ error: 'SPARK-only — briefs are 1DTE-specific.' }, { status: 400 })
  }
  const briefType = parseBriefType(req.nextUrl.searchParams.get('type')) ?? 'intraday'

  try {
    const inputs = await gatherInputs(briefType)
    return NextResponse.json({
      dry_run: true,
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
  if (bot !== 'spark') {
    return NextResponse.json({ error: 'SPARK-only.' }, { status: 400 })
  }
  const briefType = parseBriefType(req.nextUrl.searchParams.get('type')) ?? 'intraday'

  try {
    const result = await generateBrief(briefType)
    return NextResponse.json({
      id: result.id,
      brief_type: briefType,
      model: result.model,
      brief: result.brief,
      note: 'Stored in spark_market_briefs. View via GET /api/spark/briefs or /api/spark/briefs/latest.',
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // Distinguish config errors from upstream failures
    const status = /CLAUDE_API_KEY/.test(msg) ? 500 : 502
    return NextResponse.json({ error: msg }, { status })
  }
}
