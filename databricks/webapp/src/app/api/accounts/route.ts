import { NextRequest, NextResponse } from 'next/server'
import { query, t } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

const TABLE = t('ironforge_sandbox_accounts')

/** Escape a string for safe SQL interpolation. */
function esc(s: string): string {
  return s.replace(/\\/g, '\\\\').replace(/'/g, "''")
}

/** Mask an API key: show first 4 + last 4 chars. */
function mask(key: string): string {
  if (key.length <= 8) return '****'
  return `${key.slice(0, 4)}...${key.slice(-4)}`
}

/**
 * GET /api/accounts
 * Returns all sandbox accounts (active and inactive).
 */
export async function GET() {
  try {
    const rows = await query(
      `SELECT account_id, api_key, owner_name, bot_name, is_active, notes, created_at, updated_at
       FROM ${TABLE}
       ORDER BY owner_name`,
    )

    const accounts = rows.map((r: any) => ({
      account_id: r.account_id,
      api_key: mask(r.api_key || ''),
      api_key_full: r.api_key,
      owner_name: r.owner_name,
      bot_name: r.bot_name,
      is_active: r.is_active === 'true' || r.is_active === '1',
      notes: r.notes || null,
      created_at: r.created_at || null,
      updated_at: r.updated_at || null,
    }))

    return NextResponse.json({ accounts })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}

/**
 * POST /api/accounts
 * Create a new sandbox account.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { account_id, api_key, owner_name, bot_name, notes } = body

    // Validation
    if (!account_id || typeof account_id !== 'string' || !account_id.startsWith('VA')) {
      return NextResponse.json({ error: 'account_id must start with "VA"' }, { status: 400 })
    }
    if (!api_key || typeof api_key !== 'string') {
      return NextResponse.json({ error: 'api_key is required' }, { status: 400 })
    }
    if (!owner_name || typeof owner_name !== 'string') {
      return NextResponse.json({ error: 'owner_name is required' }, { status: 400 })
    }
    if (!['FLAME', 'SPARK', 'BOTH'].includes(bot_name)) {
      return NextResponse.json({ error: 'bot_name must be FLAME, SPARK, or BOTH' }, { status: 400 })
    }

    // Check for duplicate
    const existing = await query(
      `SELECT account_id FROM ${TABLE} WHERE account_id = '${esc(account_id)}' LIMIT 1`,
    )
    if (existing.length > 0) {
      return NextResponse.json({ error: 'Account ID already exists' }, { status: 409 })
    }

    await query(
      `INSERT INTO ${TABLE}
         (account_id, api_key, owner_name, bot_name, is_active, notes, created_at, updated_at)
       VALUES (
         '${esc(account_id)}', '${esc(api_key)}', '${esc(owner_name)}',
         '${esc(bot_name)}', true, ${notes ? `'${esc(notes)}'` : 'NULL'},
         CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
       )`,
    )

    return NextResponse.json({ success: true, account_id })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
