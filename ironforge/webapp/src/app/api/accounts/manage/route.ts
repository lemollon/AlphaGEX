import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable, escapeSql } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')

function maskApiKey(key: string): string {
  if (!key || key.length < 9) return '****'
  return `${key.slice(0, 4)}...${key.slice(-4)}`
}

const VALID_BOTS = ['FLAME', 'SPARK', 'INFERNO']

/**
 * Validate bot field: accepts a single bot name, "BOTH", or comma-separated list.
 * Returns normalized comma-separated string or null if invalid.
 * "BOTH" is stored as "FLAME,SPARK,INFERNO" for consistency.
 */
function validateBotField(bot: string): string | null {
  if (!bot) return null
  const trimmed = bot.trim().toUpperCase()
  if (trimmed === 'BOTH') return 'FLAME,SPARK,INFERNO'
  const parts = trimmed.split(',').map(b => b.trim()).filter(Boolean)
  if (parts.length === 0) return null
  for (const p of parts) {
    if (!VALID_BOTS.includes(p)) return null
  }
  // Deduplicate and sort for consistent storage
  const unique = Array.from(new Set(parts))
  unique.sort((a, b) => VALID_BOTS.indexOf(a) - VALID_BOTS.indexOf(b))
  return unique.join(',')
}

/** One-time migration: add capital and pdt_enabled columns if missing. */
let _migrated = false
async function ensureColumns(): Promise<void> {
  if (_migrated) return
  _migrated = true
  try {
    await dbExecute(`ALTER TABLE ${TABLE} ADD COLUMN IF NOT EXISTS capital DECIMAL(15,2) DEFAULT 10000.00`)
    await dbExecute(`ALTER TABLE ${TABLE} ADD COLUMN IF NOT EXISTS pdt_enabled BOOLEAN DEFAULT TRUE`)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[accounts] Column migration warning (non-fatal): ${msg}`)
  }
}

const SANDBOX_URL = 'https://sandbox.tradier.com/v1'

/**
 * Auto-discover Tradier sandbox account ID from an API key.
 * Calls /user/profile to get the account number.
 */
async function discoverAccountId(apiKey: string): Promise<string | null> {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    const res = await fetch(`${SANDBOX_URL}/user/profile`, {
      headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
      signal: controller.signal,
    })
    clearTimeout(timeout)
    if (!res.ok) return null
    const data = await res.json()
    let account = data.profile?.account
    if (Array.isArray(account)) account = account[0]
    return account?.account_number?.toString() || null
  } catch {
    return null
  }
}

/**
 * Auto-seed: when the DB table is empty, create rows from env vars.
 * Each env-var-based sandbox account gets auto-discovered account ID from Tradier.
 */
let _seeded = false
async function seedFromEnvVars(): Promise<void> {
  if (_seeded) return
  _seeded = true

  try {
    const existing = await dbQuery(`SELECT id FROM ${TABLE} LIMIT 1`)
    if (existing.length > 0) return // DB already has accounts — skip seeding

    // Collect env var accounts
    const envAccounts: Array<{ name: string; apiKey: string; accountIdEnv?: string }> = []

    const userKey = process.env.TRADIER_SANDBOX_KEY_USER || ''
    const mattKey = process.env.TRADIER_SANDBOX_KEY_MATT || ''
    const loganKey = process.env.TRADIER_SANDBOX_KEY_LOGAN || ''

    const userAcctId = process.env.TRADIER_SANDBOX_ACCOUNT_ID_USER || ''
    const mattAcctId = process.env.TRADIER_SANDBOX_ACCOUNT_ID_MATT || ''
    const loganAcctId = process.env.TRADIER_SANDBOX_ACCOUNT_ID_LOGAN || ''

    if (userKey) envAccounts.push({ name: 'User', apiKey: userKey, accountIdEnv: userAcctId })
    if (mattKey) envAccounts.push({ name: 'Matt', apiKey: mattKey, accountIdEnv: mattAcctId })
    if (loganKey) envAccounts.push({ name: 'Logan', apiKey: loganKey, accountIdEnv: loganAcctId })

    if (envAccounts.length === 0) return

    console.log(`[accounts] Auto-seeding ${envAccounts.length} sandbox account(s) from env vars...`)

    for (const acct of envAccounts) {
      // Use env var account ID if available, otherwise auto-discover from Tradier
      let accountId = acct.accountIdEnv
      if (!accountId) {
        accountId = await discoverAccountId(acct.apiKey) || `pending-${acct.name.toLowerCase()}`
      }

      await dbExecute(`
        INSERT INTO ${TABLE}
          (person, account_id, api_key, bot, type, is_active, capital, pdt_enabled, created_at, updated_at)
        VALUES (
          '${escapeSql(acct.name)}', '${escapeSql(accountId)}', '${escapeSql(acct.apiKey)}',
          'FLAME,SPARK,INFERNO', 'sandbox',
          TRUE, 10000.00, TRUE, NOW(), NOW()
        )
        ON CONFLICT DO NOTHING
      `)
      console.log(`[accounts] Seeded: ${acct.name} → ${accountId}`)
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[accounts] Auto-seed warning (non-fatal): ${msg}`)
  }
}

/** GET /api/accounts/manage — list all accounts grouped by type/person */
export async function GET() {
  try {
    await ensureColumns()
    await seedFromEnvVars()

    const rows = await dbQuery(`
      SELECT id, person, account_id, api_key, bot, type, is_active,
             COALESCE(capital, 10000) as capital,
             COALESCE(pdt_enabled, TRUE) as pdt_enabled,
             created_at, updated_at
      FROM ${TABLE}
      ORDER BY type, person, id
    `)

    const productionByPerson: Record<string, any[]> = {}
    const sandboxByPerson: Record<string, any[]> = {}

    for (const row of rows) {
      const acct = {
        id: parseInt(row.id),
        person: row.person,
        account_id: row.account_id,
        api_key_masked: maskApiKey(row.api_key || ''),
        bot: row.bot,
        type: row.type,
        is_active: row.is_active === true || row.is_active === 'true',
        capital: parseFloat(row.capital) || 10000,
        pdt_enabled: row.pdt_enabled === true || row.pdt_enabled === 'true',
        created_at: row.created_at || null,
        updated_at: row.updated_at || null,
      }

      if (row.type === 'sandbox') {
        const person = row.person
        if (!sandboxByPerson[person]) sandboxByPerson[person] = []
        sandboxByPerson[person].push(acct)
      } else {
        const person = row.person
        if (!productionByPerson[person]) productionByPerson[person] = []
        productionByPerson[person].push(acct)
      }
    }

    const production = Object.entries(productionByPerson).map(
      ([person, accounts]) => ({ person, accounts }),
    )

    const sandbox = Object.entries(sandboxByPerson).map(
      ([person, accounts]) => ({ person, accounts }),
    )

    return NextResponse.json({ production, sandbox })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

/** POST /api/accounts/manage — create a new account */
export async function POST(req: NextRequest) {
  try {
    await ensureColumns()

    const body = await req.json()
    const { person, account_id, api_key, bot, type } = body
    const capital = body.capital != null ? parseFloat(body.capital) : 10000
    const pdt_enabled = body.pdt_enabled != null ? body.pdt_enabled : true

    if (!person || !account_id || !api_key) {
      return NextResponse.json(
        { error: 'person, account_id, and api_key are required' },
        { status: 400 },
      )
    }
    const normalizedBot = validateBotField(bot)
    if (!normalizedBot) {
      return NextResponse.json(
        { error: 'bot must be one or more of: FLAME, SPARK, INFERNO (comma-separated or BOTH)' },
        { status: 400 },
      )
    }
    if (!['production', 'sandbox'].includes(type)) {
      return NextResponse.json(
        { error: 'type must be production or sandbox' },
        { status: 400 },
      )
    }

    // Sandbox enforcement: only one active sandbox per person
    if (type === 'sandbox') {
      const existing = await dbQuery(
        `SELECT id FROM ${TABLE} WHERE type = 'sandbox' AND person = '${escapeSql(person)}' AND is_active = TRUE LIMIT 1`,
      )
      if (existing.length > 0) {
        return NextResponse.json(
          { error: `${person} already has an active sandbox account. Each person can have only one sandbox.` },
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
        (person, account_id, api_key, bot, type, is_active, capital, pdt_enabled, created_at, updated_at)
      VALUES (
        '${escapeSql(person)}', '${escapeSql(account_id)}', '${escapeSql(api_key)}',
        '${escapeSql(normalizedBot)}', '${escapeSql(type)}',
        TRUE, ${capital}, ${pdt_enabled === true}, NOW(), NOW()
      )
    `)

    return NextResponse.json({ success: true, message: `Account ${account_id} created` })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
