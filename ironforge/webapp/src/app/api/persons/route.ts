import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, sharedTable, escapeSql } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/persons?bot=flame
 * Returns distinct person names (with optional aliases) from ironforge_accounts.
 * Optionally filters by bot assignment (e.g., only persons assigned to FLAME).
 * Used by the BotDashboard and CompareContent person dropdown filters.
 */
export async function GET(req: NextRequest) {
  try {
    const botParam = req.nextUrl.searchParams.get('bot')
    // Filter by bot assignment: ironforge_accounts.bot is comma-separated (e.g., "FLAME,SPARK,INFERNO")
    const botFilter = botParam ? `AND a.bot ILIKE '%${escapeSql(botParam)}%'` : ''

    // Return (person, account_type) pairs so dropdown can distinguish sandbox vs production
    const rows = await dbQuery(
      `SELECT DISTINCT a.person, a.type as account_type, pa.alias
       FROM ${sharedTable('ironforge_accounts')} a
       LEFT JOIN ${sharedTable('ironforge_person_aliases')} pa ON pa.person = a.person
       WHERE a.is_active = TRUE ${botFilter}
       ORDER BY a.person, a.type`,
    )
    const persons = rows.map((r) => ({
      person: r.person as string,
      alias: (r.alias as string | null) || null,
      account_type: (r.account_type as string) || 'sandbox',
    }))
    return NextResponse.json({ persons })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
