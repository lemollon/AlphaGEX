import { NextResponse } from 'next/server'
import { dbQuery, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/persons
 * Returns distinct person names from ironforge_accounts (active sandbox accounts).
 * Used by the BotDashboard person dropdown filter.
 */
export async function GET() {
  try {
    const rows = await dbQuery(
      `SELECT DISTINCT person
       FROM ${sharedTable('ironforge_accounts')}
       WHERE is_active = TRUE
       ORDER BY person`,
    )
    const persons = rows.map((r) => r.person as string)
    return NextResponse.json({ persons })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
