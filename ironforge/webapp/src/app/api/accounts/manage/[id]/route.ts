import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable, escapeSql } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')

/** PUT /api/accounts/manage/:id — update bot assignment, API key, or active status */
export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const id = parseInt(params.id)
    if (isNaN(id)) {
      return NextResponse.json({ error: 'Invalid ID' }, { status: 400 })
    }

    const existing = await dbQuery(
      `SELECT id, person, account_id FROM ${TABLE} WHERE id = ${id} LIMIT 1`,
    )
    if (existing.length === 0) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 })
    }

    const body = await req.json()
    const updates: string[] = []

    if (body.bot != null) {
      if (!['FLAME', 'SPARK', 'INFERNO', 'BOTH'].includes(body.bot)) {
        return NextResponse.json(
          { error: 'bot must be FLAME, SPARK, INFERNO, or BOTH' },
          { status: 400 },
        )
      }
      updates.push(`bot = '${escapeSql(body.bot)}'`)
    }
    if (body.api_key != null) {
      updates.push(`api_key = '${escapeSql(body.api_key)}'`)
    }
    if (body.is_active != null) {
      updates.push(`is_active = ${body.is_active}`)
    }

    if (updates.length === 0) {
      return NextResponse.json({ success: true, message: 'No changes' })
    }

    updates.push('updated_at = CURRENT_TIMESTAMP()')

    await dbExecute(`
      UPDATE ${TABLE}
      SET ${updates.join(', ')}
      WHERE id = ${id}
    `)

    return NextResponse.json({ success: true, message: 'Account updated' })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

/** DELETE /api/accounts/manage/:id — soft delete (set is_active = false) */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const id = parseInt(params.id)
    if (isNaN(id)) {
      return NextResponse.json({ error: 'Invalid ID' }, { status: 400 })
    }

    const existing = await dbQuery(
      `SELECT id, person, account_id FROM ${TABLE} WHERE id = ${id} LIMIT 1`,
    )
    if (existing.length === 0) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 })
    }

    await dbExecute(`
      UPDATE ${TABLE}
      SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP()
      WHERE id = ${id}
    `)

    const acct = existing[0]
    return NextResponse.json({
      success: true,
      message: `Account ${acct.account_id} deactivated`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
