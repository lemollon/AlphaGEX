import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable, escapeSql } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')

function maskApiKey(key: string): string {
  if (!key || key.length < 9) return '****'
  return `${key.slice(0, 4)}...${key.slice(-4)}`
}

/** GET /api/accounts/manage — list all accounts grouped by type/person */
export async function GET() {
  try {
    const rows = await dbQuery(`
      SELECT id, person, account_id, api_key, bot, type, is_active,
             created_at, updated_at
      FROM ${TABLE}
      ORDER BY type, person, id
    `)

    const productionByPerson: Record<string, any[]> = {}
    let sandboxAccount: any = null

    for (const row of rows) {
      const acct = {
        id: parseInt(row.id),
        account_id: row.account_id,
        api_key_masked: maskApiKey(row.api_key || ''),
        bot: row.bot,
        type: row.type,
        is_active: row.is_active === true || row.is_active === 'true',
        created_at: row.created_at || null,
        updated_at: row.updated_at || null,
      }

      if (row.type === 'sandbox') {
        sandboxAccount = { person: row.person, ...acct }
      } else {
        const person = row.person
        if (!productionByPerson[person]) productionByPerson[person] = []
        productionByPerson[person].push(acct)
      }
    }

    const production = Object.entries(productionByPerson).map(
      ([person, accounts]) => ({ person, accounts }),
    )

    return NextResponse.json({ production, sandbox: sandboxAccount })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

/** POST /api/accounts/manage — create a new account */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { person, account_id, api_key, bot, type } = body

    if (!person || !account_id || !api_key) {
      return NextResponse.json(
        { error: 'person, account_id, and api_key are required' },
        { status: 400 },
      )
    }
    if (!['FLAME', 'SPARK', 'INFERNO', 'BOTH'].includes(bot)) {
      return NextResponse.json(
        { error: 'bot must be FLAME, SPARK, INFERNO, or BOTH' },
        { status: 400 },
      )
    }
    if (!['production', 'sandbox'].includes(type)) {
      return NextResponse.json(
        { error: 'type must be production or sandbox' },
        { status: 400 },
      )
    }

    // Sandbox enforcement: only one active sandbox allowed
    if (type === 'sandbox') {
      const existing = await dbQuery(
        `SELECT id FROM ${TABLE} WHERE type = 'sandbox' AND is_active = TRUE LIMIT 1`,
      )
      if (existing.length > 0) {
        return NextResponse.json(
          { error: 'A sandbox account already exists' },
          { status: 409 },
        )
      }
    }

    // Check duplicate account_id
    const dupes = await dbQuery(
      `SELECT id FROM ${TABLE} WHERE account_id = '${escapeSql(account_id)}' LIMIT 1`,
    )
    if (dupes.length > 0) {
      return NextResponse.json(
        { error: 'This account ID already exists' },
        { status: 409 },
      )
    }

    await dbExecute(`
      INSERT INTO ${TABLE}
        (person, account_id, api_key, bot, type, is_active, created_at, updated_at)
      VALUES (
        '${escapeSql(person)}', '${escapeSql(account_id)}', '${escapeSql(api_key)}',
        '${escapeSql(bot)}', '${escapeSql(type)}',
        TRUE, NOW(), NOW()
      )
    `)

    return NextResponse.json({ success: true, message: `Account ${account_id} created` })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
