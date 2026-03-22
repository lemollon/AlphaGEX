import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'
const PRODUCTION_URL = 'https://api.tradier.com/v1'

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
  const unique = Array.from(new Set(parts))
  unique.sort((a, b) => VALID_BOTS.indexOf(a) - VALID_BOTS.indexOf(b))
  return unique.join(',')
}

/** One-time migration: add columns if missing. */
let _migrated = false
async function ensureColumns(): Promise<void> {
  if (_migrated) return
  _migrated = true
  try {
    await dbExecute(`ALTER TABLE ${TABLE} ADD COLUMN IF NOT EXISTS pdt_enabled BOOLEAN DEFAULT TRUE`)
    await dbExecute(`ALTER TABLE ${TABLE} ADD COLUMN IF NOT EXISTS capital_pct INTEGER DEFAULT 100`)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[accounts] Column migration warning (non-fatal): ${msg}`)
  }
}

/* ── Tradier helpers ─────────────────────────────────────────── */

async function tradierFetch(
  endpoint: string,
  apiKey: string,
  baseUrl: string = SANDBOX_URL,
): Promise<any> {
  try {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)
    const res = await fetch(`${baseUrl}${endpoint}`, {
      headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
      cache: 'no-store',
      signal: controller.signal,
    })
    clearTimeout(timeout)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

/** Discover Tradier account number from API key via /user/profile. */
async function discoverAccountId(apiKey: string): Promise<string | null> {
  const data = await tradierFetch('/user/profile', apiKey)
  if (!data) return null
  let account = data.profile?.account
  if (Array.isArray(account)) account = account[0]
  return account?.account_number?.toString() || null
}

/** Fetch live balance for one account. Returns null fields on failure. */
async function fetchLiveBalance(
  apiKey: string,
  accountNumber: string,
  accountType: string = 'sandbox',
): Promise<{
  live_balance: number | null
  live_buying_power: number | null
  open_positions: number
}> {
  const baseUrl = accountType === 'production' ? PRODUCTION_URL : SANDBOX_URL
  const [balData, posData] = await Promise.all([
    tradierFetch(`/accounts/${accountNumber}/balances`, apiKey, baseUrl),
    tradierFetch(`/accounts/${accountNumber}/positions`, apiKey, baseUrl),
  ])

  const bal = balData?.balances || {}
  const margin = bal.margin || {}
  const pdt = bal.pdt || {}

  const equity = bal.total_equity != null ? parseFloat(bal.total_equity) : null
  const obp =
    margin.option_buying_power != null ? parseFloat(margin.option_buying_power) :
    pdt.option_buying_power != null ? parseFloat(pdt.option_buying_power) :
    equity

  let posCount = 0
  if (posData?.positions?.position) {
    const posList = Array.isArray(posData.positions.position)
      ? posData.positions.position
      : [posData.positions.position]
    posCount = posList.length
  }

  return { live_balance: equity, live_buying_power: obp, open_positions: posCount }
}

/* ── Balance cache (60s TTL) ─────────────────────────────────── */

interface CachedBalance {
  live_balance: number | null
  live_buying_power: number | null
  open_positions: number
  fetched_at: number
}

const _balanceCache: Record<string, CachedBalance> = {}
const CACHE_TTL_MS = 60_000

async function getLiveBalance(
  apiKey: string,
  accountId: string,
  accountType: string = 'sandbox',
): Promise<CachedBalance> {
  const cacheKey = `${accountId}:${apiKey.slice(-6)}`
  const cached = _balanceCache[cacheKey]
  if (cached && Date.now() - cached.fetched_at < CACHE_TTL_MS) return cached

  const result = await fetchLiveBalance(apiKey, accountId, accountType)
  const entry: CachedBalance = { ...result, fetched_at: Date.now() }
  _balanceCache[cacheKey] = entry
  return entry
}

/* ── Auto-seed from env vars ─────────────────────────────────── */

let _seeded = false
async function seedFromEnvVars(): Promise<void> {
  if (_seeded) return
  _seeded = true

  try {
    const existing = await dbQuery(`SELECT id FROM ${TABLE} LIMIT 1`)
    if (existing.length > 0) return

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
      let accountId = acct.accountIdEnv
      if (!accountId) {
        accountId = await discoverAccountId(acct.apiKey) || `pending-${acct.name.toLowerCase()}`
      }

      await dbExecute(`
        INSERT INTO ${TABLE}
          (person, account_id, api_key, bot, type, is_active, capital_pct, pdt_enabled, created_at, updated_at)
        VALUES ($1, $2, $3, 'FLAME,SPARK,INFERNO', 'sandbox', TRUE, 100, TRUE, NOW(), NOW())
        ON CONFLICT DO NOTHING
      `, [acct.name, accountId, acct.apiKey])
      console.log(`[accounts] Seeded: ${acct.name} → ${accountId}`)
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    console.warn(`[accounts] Auto-seed warning (non-fatal): ${msg}`)
  }
}

/* ── GET /api/accounts/manage ────────────────────────────────── */

export async function GET() {
  try {
    await ensureColumns()
    await seedFromEnvVars()

    const rows = await dbQuery(`
      SELECT id, person, account_id, api_key, bot, type, is_active,
             COALESCE(capital_pct, 100) as capital_pct,
             COALESCE(pdt_enabled, TRUE) as pdt_enabled,
             created_at, updated_at
      FROM ${TABLE}
      ORDER BY type, person, id
    `)

    // Fetch live balances in parallel for all active accounts
    const balancePromises: Array<Promise<void>> = []
    const liveData: Record<number, CachedBalance> = {}

    for (const row of rows) {
      const isActive = row.is_active === true || row.is_active === 'true'
      if (isActive && row.api_key) {
        const rowId = parseInt(row.id)
        balancePromises.push(
          getLiveBalance(row.api_key, row.account_id, row.type || 'sandbox').then(bal => {
            liveData[rowId] = bal
          }),
        )
      }
    }

    await Promise.all(balancePromises)

    // Trace live balances
    const activeCount = Object.keys(liveData).length
    console.log(`[accounts] GET: Fetched live balances for ${activeCount} active account(s)`)

    const productionByPerson: Record<string, any[]> = {}
    const sandboxByPerson: Record<string, any[]> = {}

    for (const row of rows) {
      const rowId = parseInt(row.id)
      const capitalPct = parseInt(row.capital_pct) || 100
      const live = liveData[rowId]
      const liveBalance = live?.live_balance ?? null
      const allocatedCapital = liveBalance != null
        ? Math.round(liveBalance * capitalPct / 100 * 100) / 100
        : null

      const acct = {
        id: rowId,
        person: row.person,
        account_id: row.account_id,
        api_key_masked: maskApiKey(row.api_key || ''),
        bot: row.bot,
        type: row.type,
        is_active: row.is_active === true || row.is_active === 'true',
        capital_pct: capitalPct,
        pdt_enabled: row.pdt_enabled === true || row.pdt_enabled === 'true',
        live_balance: liveBalance,
        live_buying_power: live?.live_buying_power ?? null,
        open_positions: live?.open_positions ?? 0,
        allocated_capital: allocatedCapital,
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

/* ── POST /api/accounts/manage ───────────────────────────────── */

export async function POST(req: NextRequest) {
  try {
    await ensureColumns()

    const body = await req.json()
    const { person, account_id, api_key, bot, type } = body
    const capitalPct = body.capital_pct != null ? parseInt(body.capital_pct) : 100
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
    if (capitalPct < 1 || capitalPct > 100) {
      return NextResponse.json(
        { error: 'capital_pct must be between 1 and 100' },
        { status: 400 },
      )
    }

    // Sandbox enforcement: only one active sandbox per person
    if (type === 'sandbox') {
      const existing = await dbQuery(
        `SELECT id FROM ${TABLE} WHERE type = 'sandbox' AND person = $1 AND is_active = TRUE LIMIT 1`,
        [person],
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
      `SELECT id FROM ${TABLE} WHERE account_id = $1 LIMIT 1`,
      [account_id],
    )
    if (dupes.length > 0) {
      return NextResponse.json(
        { error: 'This account ID already exists' },
        { status: 409 },
      )
    }

    // Validate API key against correct Tradier API (sandbox or production)
    const skipTest = req.nextUrl.searchParams.get('skip_test') === 'true'
    if (!skipTest) {
      const validateUrl = type === 'production' ? PRODUCTION_URL : SANDBOX_URL
      const profile = await tradierFetch('/user/profile', api_key, validateUrl)
      if (!profile) {
        const label = type === 'production' ? 'Tradier production API' : 'Tradier sandbox API'
        return NextResponse.json(
          { error: `API key validation failed — cannot reach ${label} with this key` },
          { status: 400 },
        )
      }
    }

    await dbExecute(`
      INSERT INTO ${TABLE}
        (person, account_id, api_key, bot, type, is_active, capital_pct, pdt_enabled, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, TRUE, $6, $7, NOW(), NOW())
    `, [person, account_id, api_key, normalizedBot, type, capitalPct, pdt_enabled === true])

    // Invalidate sandbox account cache so scanner picks up the new account immediately
    try {
      const { reloadSandboxAccounts } = await import('@/lib/tradier')
      await reloadSandboxAccounts()
    } catch { /* non-fatal */ }

    // Capital minimum warning (only relevant for sandbox — production is monitoring-only)
    const estimatedAllocation = 10000 * capitalPct / 100
    const warning = type === 'sandbox' && estimatedAllocation < 500
      ? `Allocated capital will be ~$${Math.round(estimatedAllocation)} — below recommended $500 minimum`
      : undefined

    return NextResponse.json({ success: true, message: `Account ${account_id} created`, warning })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
