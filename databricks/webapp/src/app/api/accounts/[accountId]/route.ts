import { NextRequest, NextResponse } from 'next/server'
import { query, t } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

const TABLE = t('ironforge_sandbox_accounts')

function esc(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "''")
}

/**
 * PUT /api/accounts/[accountId]
 * Update an existing sandbox account.
 */
export async function PUT(
  req: NextRequest,
  { params }: { params: { accountId: string } },
) {
  const accountId = params.accountId
  if (!accountId) {
    return NextResponse.json({ error: 'Missing accountId' }, { status: 400 })
  }

  try {
    const body = await req.json()
    const allowed = ['api_key', 'owner_name', 'bot_name', 'is_active', 'notes']
    const sets: string[] = []

    for (const key of allowed) {
      if (body[key] === undefined) continue
      if (key === 'bot_name' && !['FLAME', 'SPARK', 'BOTH'].includes(body[key])) {
        return NextResponse.json({ error: 'bot_name must be FLAME, SPARK, or BOTH' }, { status: 400 })
      }
      if (key === 'is_active') {
        sets.push(`is_active = ${Boolean(body[key])}`)
      } else if (body[key] === null) {
        sets.push(`${key} = NULL`)
      } else {
        sets.push(`${key} = '${esc(String(body[key]))}'`)
      }
    }

    if (sets.length === 0) {
      return NextResponse.json({ error: 'No fields to update' }, { status: 400 })
    }

    sets.push('updated_at = CURRENT_TIMESTAMP()')

    await query(
      `UPDATE ${TABLE}
       SET ${sets.join(', ')}
       WHERE account_id = '${esc(accountId)}'`,
    )

    return NextResponse.json({ success: true, account_id: accountId })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

/**
 * DELETE /api/accounts/[accountId]
 * Soft-delete: sets is_active = false.
 */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: { accountId: string } },
) {
  const accountId = params.accountId
  if (!accountId) {
    return NextResponse.json({ error: 'Missing accountId' }, { status: 400 })
  }

  try {
    await query(
      `UPDATE ${TABLE}
       SET is_active = false, updated_at = CURRENT_TIMESTAMP()
       WHERE account_id = '${esc(accountId)}'`,
    )

    return NextResponse.json({ success: true, account_id: accountId, is_active: false })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
