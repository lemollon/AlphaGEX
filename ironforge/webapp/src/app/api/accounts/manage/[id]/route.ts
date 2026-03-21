import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable, escapeSql } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')

const VALID_BOTS = ['FLAME', 'SPARK', 'INFERNO']

function validateBotField(bot: string): string | null {
  if (!bot) return null
  const trimmed = bot.trim().toUpperCase()
  if (trimmed === 'BOTH') return 'FLAME,SPARK,INFERNO'
  const parts = trimmed.split(',').map(b => b.trim()).filter(Boolean)
  if (parts.length === 0) return null
  for (const p of parts) {
    if (!VALID_BOTS.includes(p)) return null
  }
  const unique = Array.from(new Set(parts))
  unique.sort((a, b) => VALID_BOTS.indexOf(a) - VALID_BOTS.indexOf(b))
  return unique.join(',')
}

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
      const normalizedBot = validateBotField(body.bot)
      if (!normalizedBot) {
        return NextResponse.json(
          { error: 'bot must be one or more of: FLAME, SPARK, INFERNO (comma-separated or BOTH)' },
          { status: 400 },
        )
      }
      updates.push(`bot = '${escapeSql(normalizedBot)}'`)
    }
    if (body.api_key != null) {
      updates.push(`api_key = '${escapeSql(body.api_key)}'`)
    }
    if (body.is_active != null) {
      updates.push(`is_active = ${body.is_active}`)
    }
    if (body.capital_pct != null) {
      const pct = parseInt(body.capital_pct)
      if (isNaN(pct) || pct < 1 || pct > 100) {
        return NextResponse.json(
          { error: 'capital_pct must be between 1 and 100' },
          { status: 400 },
        )
      }
      updates.push(`capital_pct = ${pct}`)
    }
    if (body.pdt_enabled != null) {
      updates.push(`pdt_enabled = ${body.pdt_enabled === true}`)
    }

    if (updates.length === 0) {
      return NextResponse.json({ success: true, message: 'No changes' })
    }

    updates.push('updated_at = NOW()')

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
      SET is_active = FALSE, updated_at = NOW()
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
