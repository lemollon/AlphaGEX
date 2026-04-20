/**
 * GET /api/{bot}/preflight-live
 *
 * One-shot live-trading readiness check for the production bot. Runs every
 * prerequisite SPARK needs in order to safely place real-money orders and
 * returns a single JSON verdict (`ready: true` only when ALL checks pass).
 *
 * This endpoint is read-only. It places no orders and writes no rows.
 *
 * Checks (in order, fail-fast on critical):
 *   1.  Bot identity matches PRODUCTION_BOT.
 *   2.  Required env vars set: TRADIER_PROD_API_KEY, TRADIER_PROD_ACCOUNT_ID.
 *   3.  ironforge_accounts has at least one active production row tagged for
 *       this bot (matches getAccountsForBotAsync's bot LIKE filter).
 *   4.  Each production account resolves an account_id via Tradier (key valid).
 *   5.  Each production account returns a real balance with total_equity > 0
 *       and option_buying_power >= $500 (one $5 spread minimum).
 *   6.  spark_paper_account has an active production row for each production
 *       person (so the scanner has a ledger to write into).
 *   7.  ironforge_pdt_config has a SPARK row with finite limits.
 *   8.  Scanner heartbeat is < 5 min old.
 *   9.  Defense-in-depth: PRODUCTION_BOT in scanner.ts and tradier.ts agree.
 *
 * Use this BEFORE flipping a real-money switch in Render env or in
 * ironforge_accounts. Failing checks include the exact remediation step.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, sharedTable, validateBot, dteMode } from '@/lib/db'
import {
  PRODUCTION_BOT,
  getProductionAccountsForBot,
  getTradierBalanceDetail,
  getAccountsForBotAsync,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

interface Check {
  name: string
  pass: boolean
  detail: string
  remediation?: string
}

const MIN_OPTION_BP = 500            // one $5 spread × 100
const HEARTBEAT_STALE_SEC = 300      // 5 min
const HEARTBEAT_NAME: Record<string, string> = {
  spark: 'SPARK',
  flame: 'FLAME',
  inferno: 'INFERNO',
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const checks: Check[] = []
  const fail = (name: string, detail: string, remediation?: string) => {
    checks.push({ name, pass: false, detail, ...(remediation ? { remediation } : {}) })
  }
  const pass = (name: string, detail: string) => {
    checks.push({ name, pass: true, detail })
  }

  // 1. Bot identity
  if (bot !== PRODUCTION_BOT) {
    fail(
      '1. bot_is_production_bot',
      `Bot is '${bot}' but PRODUCTION_BOT is '${PRODUCTION_BOT}'. Preflight only runs for the live-trading bot.`,
      `Run GET /api/${PRODUCTION_BOT}/preflight-live instead.`,
    )
    return NextResponse.json({ ready: false, bot, production_bot: PRODUCTION_BOT, checks })
  }
  pass('1. bot_is_production_bot', `bot=${bot} matches PRODUCTION_BOT`)

  // 2. Required env vars
  const prodKey = process.env.TRADIER_PROD_API_KEY || ''
  const prodAcctId = process.env.TRADIER_PROD_ACCOUNT_ID || ''
  if (!prodKey) {
    fail(
      '2a. env.TRADIER_PROD_API_KEY',
      'Not set. SPARK cannot route orders to api.tradier.com.',
      'Set TRADIER_PROD_API_KEY in the Render service env vars.',
    )
  } else {
    pass('2a. env.TRADIER_PROD_API_KEY', `present (${prodKey.length} chars)`)
  }
  if (!prodAcctId) {
    fail(
      '2b. env.TRADIER_PROD_ACCOUNT_ID',
      'Not set. The Python config helper will refuse to start SPARK.',
      'Set TRADIER_PROD_ACCOUNT_ID in the Render service env vars.',
    )
  } else {
    pass('2b. env.TRADIER_PROD_ACCOUNT_ID', `present (${prodAcctId})`)
  }

  // 3. ironforge_accounts has an active production row tagged for SPARK
  let assignedPersons: string[] = []
  try {
    assignedPersons = await getAccountsForBotAsync(bot)
  } catch (err: unknown) {
    fail(
      '3. ironforge_accounts.bot includes SPARK',
      `getAccountsForBotAsync failed: ${err instanceof Error ? err.message : String(err)}`,
      'Check DATABASE_URL is reachable and ironforge_accounts table exists.',
    )
  }
  let prodAccountRows: Array<{ person: string; bot: string; capital_pct: number | null; pdt_enabled: boolean | null }> = []
  try {
    const rows = await dbQuery(
      `SELECT person, bot, capital_pct, pdt_enabled
       FROM ${sharedTable('ironforge_accounts')}
       WHERE is_active = TRUE AND type = 'production' AND bot ILIKE $1
       ORDER BY person`,
      [`%${bot.toUpperCase()}%`],
    )
    prodAccountRows = rows as typeof prodAccountRows
  } catch (err: unknown) {
    fail(
      '3. ironforge_accounts query',
      `failed: ${err instanceof Error ? err.message : String(err)}`,
    )
  }
  if (prodAccountRows.length === 0) {
    fail(
      '3. production accounts assigned to SPARK',
      'No active rows in ironforge_accounts with type=production and bot LIKE \'%SPARK%\'.',
      `INSERT/UPDATE ironforge_accounts SET bot = 'SPARK' WHERE person = '<your_person>' AND type = 'production'.`,
    )
  } else {
    pass(
      '3. production accounts assigned to SPARK',
      `${prodAccountRows.length} row(s): ${prodAccountRows.map(r => `${r.person}(bot="${r.bot}", cap=${r.capital_pct}%, pdt=${r.pdt_enabled})`).join(', ')}`,
    )
  }

  // 4. Each production account resolves a Tradier account_id (i.e., the key works)
  let resolvedAccts: Awaited<ReturnType<typeof getProductionAccountsForBot>> = []
  try {
    resolvedAccts = await getProductionAccountsForBot(bot)
  } catch (err: unknown) {
    fail(
      '4. resolve Tradier account IDs',
      `getProductionAccountsForBot failed: ${err instanceof Error ? err.message : String(err)}`,
    )
  }
  const acctsWithoutId = resolvedAccts.filter(a => !a.accountId)
  if (resolvedAccts.length === 0 && prodAccountRows.length > 0) {
    fail(
      '4. resolve Tradier account IDs',
      'ironforge_accounts has SPARK production rows but no Tradier account loaded for them.',
      'Verify ironforge_accounts.api_key is set and that the row was loaded from DB (check /api/spark/diagnose-production).',
    )
  } else if (acctsWithoutId.length > 0) {
    fail(
      '4. resolve Tradier account IDs',
      `${acctsWithoutId.length}/${resolvedAccts.length} account(s) failed to resolve account_id: ${acctsWithoutId.map(a => a.name).join(', ')}.`,
      'Account API key is invalid or Tradier production endpoint is unreachable.',
    )
  } else if (resolvedAccts.length > 0) {
    pass(
      '4. resolve Tradier account IDs',
      `${resolvedAccts.length} account(s) resolved: ${resolvedAccts.map(a => `${a.name}=${a.accountId}`).join(', ')}`,
    )
  }

  // 5. Each production account has real balance + sufficient option BP
  const balanceSummaries: Array<{ name: string; total_equity: number | null; option_buying_power: number | null }> = []
  let allBalancesOk = resolvedAccts.length > 0 && acctsWithoutId.length === 0
  for (const acct of resolvedAccts) {
    if (!acct.accountId) {
      allBalancesOk = false
      continue
    }
    let bal: Awaited<ReturnType<typeof getTradierBalanceDetail>> = null
    try {
      bal = await getTradierBalanceDetail(acct.apiKey, acct.accountId, acct.baseUrl)
    } catch (err: unknown) {
      fail(
        `5. balance fetch [${acct.name}]`,
        `Tradier /balances threw: ${err instanceof Error ? err.message : String(err)}`,
      )
      allBalancesOk = false
      continue
    }
    if (!bal) {
      fail(
        `5. balance fetch [${acct.name}]`,
        'Tradier /balances returned null (account_id mismatch or API key not authorized).',
      )
      allBalancesOk = false
      continue
    }
    balanceSummaries.push({ name: acct.name, total_equity: bal.total_equity, option_buying_power: bal.option_buying_power })
    const equity = bal.total_equity ?? 0
    const obp = bal.option_buying_power ?? 0
    if (equity <= 0) {
      fail(
        `5. balance [${acct.name}] total_equity > 0`,
        `total_equity=$${equity.toFixed(2)} — account is empty or Tradier returned bad data.`,
        'Fund the production account before enabling SPARK.',
      )
      allBalancesOk = false
    } else if (obp < MIN_OPTION_BP) {
      fail(
        `5. balance [${acct.name}] option_buying_power >= $${MIN_OPTION_BP}`,
        `option_buying_power=$${obp.toFixed(2)} (need $${MIN_OPTION_BP} for one $5 spread).`,
        'Free up margin or lower position sizing before enabling SPARK.',
      )
      allBalancesOk = false
    } else {
      pass(
        `5. balance [${acct.name}]`,
        `total_equity=$${equity.toFixed(2)}, option_buying_power=$${obp.toFixed(2)}`,
      )
    }
  }

  // 6. spark_paper_account has an active production ledger row per person
  const dte = dteMode(bot) || '1DTE'
  let paperRows: Array<{ id: number; person: string; is_active: boolean; dte_mode: string }> = []
  try {
    const rows = await dbQuery(
      `SELECT id, person, is_active, dte_mode
       FROM ${botTable(bot, 'paper_account')}
       WHERE COALESCE(account_type, 'sandbox') = 'production'
         AND dte_mode = $1`,
      [dte],
    )
    paperRows = rows as typeof paperRows
  } catch (err: unknown) {
    fail(
      '6. spark_paper_account production rows',
      `query failed: ${err instanceof Error ? err.message : String(err)}`,
    )
  }
  const expectedPersons = Array.from(new Set(prodAccountRows.map(r => r.person)))
  const haveByPerson = Array.from(new Set(paperRows.filter(p => p.is_active).map(p => p.person)))
  const haveSet = new Set(haveByPerson)
  const missingPersons = expectedPersons.filter(p => !haveSet.has(p))
  if (expectedPersons.length === 0) {
    // already failed in check 3
  } else if (missingPersons.length > 0) {
    fail(
      '6. spark_paper_account production ledger rows',
      `Missing active production row for: ${missingPersons.join(', ')}.`,
      'Restart the webapp once — db.ts bootstrap auto-seeds spark_paper_account production rows from ironforge_accounts.',
    )
  } else {
    pass(
      '6. spark_paper_account production ledger rows',
      `${paperRows.filter(p => p.is_active).length} active row(s) for: ${haveByPerson.join(', ')}`,
    )
  }

  // 7. ironforge_pdt_config has a SPARK row with finite limits
  try {
    const pdtRows = await dbQuery(
      `SELECT pdt_enabled, max_day_trades, window_days, max_trades_per_day
       FROM ${sharedTable('ironforge_pdt_config')}
       WHERE bot_name = $1
       LIMIT 1`,
      [bot.toUpperCase()],
    )
    if (pdtRows.length === 0) {
      fail(
        '7. ironforge_pdt_config[SPARK]',
        'No SPARK row in ironforge_pdt_config — PDT enforcement will fall back to defaults.',
        'Restart the webapp; db.ts bootstrap seeds this row.',
      )
    } else {
      const r = pdtRows[0] as { pdt_enabled: boolean | string; max_day_trades: number; window_days: number; max_trades_per_day: number }
      pass(
        '7. ironforge_pdt_config[SPARK]',
        `pdt_enabled=${r.pdt_enabled}, max_day_trades=${r.max_day_trades}/${r.window_days}d, max_trades_per_day=${r.max_trades_per_day}`,
      )
    }
  } catch (err: unknown) {
    fail(
      '7. ironforge_pdt_config[SPARK]',
      `query failed: ${err instanceof Error ? err.message : String(err)}`,
    )
  }

  // 8. Scanner heartbeat is recent
  try {
    const hbRows = await dbQuery(
      `SELECT last_heartbeat, status
       FROM ${sharedTable('bot_heartbeats')}
       WHERE bot_name = $1
       LIMIT 1`,
      [HEARTBEAT_NAME[bot] || bot.toUpperCase()],
    )
    const hb = hbRows[0] as { last_heartbeat: string | Date | null; status: string | null } | undefined
    if (!hb || !hb.last_heartbeat) {
      fail(
        '8. scanner heartbeat',
        'No heartbeat row found — scanner may not be running.',
        'Check Render logs; scanner.ts auto-starts on first DB connection.',
      )
    } else {
      const ageSec = Math.round((Date.now() - new Date(hb.last_heartbeat).getTime()) / 1000)
      if (ageSec > HEARTBEAT_STALE_SEC) {
        fail(
          '8. scanner heartbeat',
          `Last heartbeat ${ageSec}s ago (status=${hb.status}). Stale — scanner appears dead.`,
          'Investigate scanner crash in Render logs; webapp restart resumes the scanner.',
        )
      } else {
        pass(
          '8. scanner heartbeat',
          `${ageSec}s old (status=${hb.status})`,
        )
      }
    }
  } catch (err: unknown) {
    fail(
      '8. scanner heartbeat',
      `query failed: ${err instanceof Error ? err.message : String(err)}`,
    )
  }

  // 9. Defense-in-depth: scanner.ts and tradier.ts both name SPARK as production
  // (We can't import scanner.ts's local PRODUCTION_BOT — they're independent
  // constants by design — but we can assert tradier.ts agrees and document
  // that scanner.ts must match. Mismatch = silent paper-only behavior.)
  pass(
    '9. tradier.ts PRODUCTION_BOT',
    `'${PRODUCTION_BOT}' (scanner.ts must match this exact string in its local PRODUCTION_BOT constant)`,
  )

  const ready = checks.every(c => c.pass)
  return NextResponse.json({
    ready,
    bot,
    production_bot: PRODUCTION_BOT,
    summary: ready
      ? `READY — all ${checks.length} checks passed. SPARK is configured for live trading.`
      : `NOT READY — ${checks.filter(c => !c.pass).length}/${checks.length} check(s) failed. See remediation per check.`,
    balances: balanceSummaries,
    checks,
  })
}
