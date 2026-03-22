import { NextResponse } from 'next/server'
import { dbQuery, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/persons
 * Returns distinct person names (with optional aliases) from ironforge_accounts.
 * Used by the BotDashboard and CompareContent person dropdown filters.
 */
export async function GET() {
  try {
    const rows = await dbQuery(
      `SELECT DISTINCT a.person, pa.alias
       FROM ${sharedTable('ironforge_accounts')} a
       LEFT JOIN ${sharedTable('ironforge_person_aliases')} pa ON pa.person = a.person
       WHERE a.is_active = TRUE
       ORDER BY a.person`,
    )
    const persons = rows.map((r) => ({
      person: r.person as string,
      alias: (r.alias as string | null) || null,
    }))
    return NextResponse.json({ persons })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
