import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable } from '@/lib/db'

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
      `SELECT id, person, account_id FROM ${TABLE} WHERE id = $1 LIMIT 1`,
      [id],
    )
    if (existing.length === 0) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 })
    }

    const body = await req.json()

    // Block account type changes — type is immutable after creation
    if (body.type != null) {
      return NextResponse.json(
        { error: 'Account type cannot be changed after creation' },
        { status: 400 },
      )
    }

    const setClauses: string[] = []
    const values: any[] = []
    let paramIndex = 1

    if (body.bot != null) {
      const normalizedBot = validateBotField(body.bot)
      if (!normalizedBot) {
        return NextResponse.json(
          { error: 'bot must be one or more of: FLAME, SPARK, INFERNO (comma-separated or BOTH)' },
          { status: 400 },
        )
      }
      setClauses.push(`bot = $${paramIndex++}`)
      values.push(normalizedBot)
    }
    if (body.api_key != null) {
      setClauses.push(`api_key = $${paramIndex++}`)
      values.push(body.api_key)
    }
    if (body.is_active != null) {
      setClauses.push(`is_active = $${paramIndex++}`)
      values.push(body.is_active === true)
    }
    if (body.capital_pct != null) {
      const pct = parseInt(body.capital_pct)
      if (isNaN(pct) || pct < 1 || pct > 100) {
        return NextResponse.json(
          { error: 'capital_pct must be between 1 and 100' },
          { status: 400 },
        )
      }
      setClauses.push(`capital_pct = $${paramIndex++}`)
      values.push(pct)
    }
    if (body.pdt_enabled != null) {
      setClauses.push(`pdt_enabled = $${paramIndex++}`)
      values.push(body.pdt_enabled === true)
    }

    if (setClauses.length === 0) {
      return NextResponse.json({ success: true, message: 'No changes' })
    }

    setClauses.push('updated_at = NOW()')
    values.push(id)

    await dbExecute(`
      UPDATE ${TABLE}
      SET ${setClauses.join(', ')}
      WHERE id = $${paramIndex}
    `, values)

    // Invalidate sandbox account cache so scanner picks up changes immediately
    try {
      const { reloadSandboxAccounts } = await import('@/lib/tradier')
      await reloadSandboxAccounts()
    } catch { /* non-fatal */ }

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
      `SELECT id, person, account_id, api_key, bot, type FROM ${TABLE} WHERE id = $1 LIMIT 1`,
      [id],
    )
    if (existing.length === 0) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 })
    }

    await dbExecute(`
      UPDATE ${TABLE}
      SET is_active = FALSE, updated_at = NOW()
      WHERE id = $1
    `, [id])

    const acct = existing[0]

    // Immediate cleanup: close any open Tradier sandbox positions for this account
    let closedPositions = 0
    if (acct.type === 'sandbox' && acct.api_key) {
      try {
        const { closeAllSandboxPositions } = await import('@/lib/tradier')
        closedPositions = await closeAllSandboxPositions(acct.api_key)
        if (closedPositions > 0) {
          console.log(`[accounts] Closed ${closedPositions} Tradier position(s) for deactivated account ${acct.account_id}`)
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        console.warn(`[accounts] Failed to close positions for ${acct.account_id}: ${msg}`)
      }
    }

    // Invalidate sandbox account cache
    try {
      const { reloadSandboxAccounts } = await import('@/lib/tradier')
      await reloadSandboxAccounts()
    } catch { /* non-fatal */ }

    const closeNote = closedPositions > 0 ? ` (${closedPositions} position(s) closed)` : ''
    return NextResponse.json({
      success: true,
      message: `Account ${acct.account_id} deactivated${closeNote}`,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
