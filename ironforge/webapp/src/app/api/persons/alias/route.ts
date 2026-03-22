import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * PUT /api/persons/alias
 * Set or clear the display alias for a person.
 * Body: { person: string, alias: string | null }
 */
export async function PUT(req: NextRequest) {
  try {
    const body = await req.json()
    const { person } = body
    const alias: string | null = body.alias?.trim() || null

    if (!person || typeof person !== 'string') {
      return NextResponse.json({ error: 'person is required' }, { status: 400 })
    }

    // Verify the person exists in ironforge_accounts
    const existing = await dbQuery(
      `SELECT 1 FROM ${sharedTable('ironforge_accounts')} WHERE person = $1 LIMIT 1`,
      [person],
    )
    if (existing.length === 0) {
      return NextResponse.json({ error: `Person "${person}" not found` }, { status: 404 })
    }

    // Upsert alias
    await dbExecute(
      `INSERT INTO ${sharedTable('ironforge_person_aliases')} (person, alias, updated_at)
       VALUES ($1, $2, NOW())
       ON CONFLICT (person) DO UPDATE SET alias = $2, updated_at = NOW()`,
      [person, alias],
    )

    return NextResponse.json({ success: true, person, alias })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
