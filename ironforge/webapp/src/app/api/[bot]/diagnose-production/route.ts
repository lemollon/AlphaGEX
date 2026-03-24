import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, sharedTable, validateBot, dteMode, escapeSql } from '@/lib/db'
import {
  getLoadedSandboxAccountsAsync,
  getSandboxBuyingPower,
  getCapitalPctForAccount,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * GET /api/flame/diagnose-production
 *
 * Simulates the exact production order path without placing any orders.
 * Shows every gate and exactly where production gets blocked.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const checks: Array<{ step: string; pass: boolean; detail: string }> = []
  const dte = dteMode(bot)

  // Step 1: Tradier configured?
  const configured = isConfigured()
  checks.push({
    step: '1. Tradier configured',
    pass: configured,
    detail: configured ? 'TRADIER_API_KEY set' : 'TRADIER_API_KEY NOT SET — nothing works',
  })
  if (!configured) {
    return NextResponse.json({ checks, verdict: 'BLOCKED at step 1' })
  }

  // Step 2: Load all accounts (sandbox + production)
  let allAccounts: Array<{ name: string; apiKey: string; baseUrl: string; type: 'sandbox' | 'production' }> = []
  try {
    allAccounts = await getLoadedSandboxAccountsAsync()
  } catch (err: unknown) {
    checks.push({
      step: '2. Load accounts from DB',
      pass: false,
      detail: `FAILED: ${err instanceof Error ? err.message : String(err)}`,
    })
    return NextResponse.json({ checks, verdict: 'BLOCKED at step 2' })
  }

  const productionAccounts = allAccounts.filter(a => a.type === 'production')
  const sandboxAccounts = allAccounts.filter(a => a.type !== 'production')
  checks.push({
    step: '2. Load accounts from DB',
    pass: productionAccounts.length > 0,
    detail: `${allAccounts.length} total (${sandboxAccounts.length} sandbox, ${productionAccounts.length} production). ` +
      `Names: ${allAccounts.map(a => `${a.name}[${a.type}]`).join(', ')}`,
  })

  if (productionAccounts.length === 0) {
    return NextResponse.json({
      checks,
      verdict: 'BLOCKED at step 2 — no production accounts in _sandboxAccounts. ' +
        'Check ironforge_accounts table for type=production rows.',
    })
  }

  // Step 3: Bot filter — does ironforge_accounts have production rows with bot matching FLAME?
  const botUpper = bot.toUpperCase()
  let botFilterRows: any[] = []
  try {
    botFilterRows = await dbQuery(
      `SELECT person, type, bot, is_active, capital_pct
       FROM ${sharedTable('ironforge_accounts')}
       WHERE is_active = TRUE AND type IN ('sandbox', 'production')
         AND (bot = $1 OR bot LIKE '%' || $1 || '%' OR bot = 'BOTH'
              OR bot = 'FLAME,SPARK,INFERNO')
       ORDER BY person, type`,
      [botUpper],
    )
  } catch (err: unknown) {
    checks.push({
      step: '3. Bot filter query',
      pass: false,
      detail: `DB QUERY FAILED: ${err instanceof Error ? err.message : String(err)}`,
    })
    return NextResponse.json({ checks, verdict: 'BLOCKED at step 3' })
  }

  const prodBotRows = botFilterRows.filter((r: any) => r.type === 'production')
  checks.push({
    step: '3. Bot filter query',
    pass: prodBotRows.length > 0,
    detail: `${botFilterRows.length} rows matched (${prodBotRows.length} production). ` +
      `Rows: ${botFilterRows.map((r: any) => `${r.person}[${r.type}] bot="${r.bot}" capital_pct=${r.capital_pct}`).join('; ')}`,
  })

  if (prodBotRows.length === 0) {
    return NextResponse.json({
      checks,
      verdict: 'BLOCKED at step 3 — no production rows match bot filter. ' +
        'Check ironforge_accounts.bot column for production row — must contain "FLAME".',
    })
  }

  // Step 4: Match bot filter results against loaded _sandboxAccounts
  const allowedKeys = new Set(botFilterRows.map((r: any) => `${r.person}:${r.type}`))
  const eligibleAccounts = allAccounts.filter(a => allowedKeys.has(`${a.name}:${a.type ?? 'sandbox'}`))
  const eligibleProd = eligibleAccounts.filter(a => a.type === 'production')

  checks.push({
    step: '4. Match filter → loaded accounts',
    pass: eligibleProd.length > 0,
    detail: `allowedKeys=[${Array.from(allowedKeys).join(', ')}], ` +
      `eligible=[${eligibleAccounts.map(a => `${a.name}:${a.type}`).join(', ')}], ` +
      `production=${eligibleProd.length}`,
  })

  if (eligibleProd.length === 0) {
    // Check for name mismatch
    const prodNames = productionAccounts.map(a => a.name)
    const filterNames = prodBotRows.map((r: any) => r.person)
    return NextResponse.json({
      checks,
      verdict: `BLOCKED at step 4 — name mismatch. DB filter has person=[${filterNames.join(',')}] ` +
        `but loaded production accounts have name=[${prodNames.join(',')}]. These must match exactly.`,
    })
  }

  // Step 5: For each production account, check API key validity + buying power
  for (const acct of eligibleProd) {
    const acctLabel = `${acct.name}[production]`

    // 5a: Get account ID (validates API key)
    let accountId: string | null = null
    try {
      const { getAccountIdForKey } = await import('@/lib/tradier')
      accountId = await (getAccountIdForKey as any)(acct.apiKey, acct.baseUrl)
    } catch (err: unknown) {
      checks.push({
        step: `5a. API key validation (${acctLabel})`,
        pass: false,
        detail: `getAccountIdForKey FAILED: ${err instanceof Error ? err.message : String(err)}`,
      })
      continue
    }
    checks.push({
      step: `5a. API key validation (${acctLabel})`,
      pass: accountId != null,
      detail: accountId ? `accountId=${accountId}` : 'RETURNED NULL — API key invalid or Tradier unreachable',
    })
    if (!accountId) continue

    // 5b: Get buying power
    let bp: number | null = null
    try {
      bp = await getSandboxBuyingPower(acct.apiKey, accountId, acct.baseUrl)
    } catch (err: unknown) {
      checks.push({
        step: `5b. Buying power (${acctLabel})`,
        pass: false,
        detail: `FAILED: ${err instanceof Error ? err.message : String(err)}`,
      })
      continue
    }
    const spreadWidth = 5 // $5 spread
    const brokerMargin = spreadWidth * 100 // $500
    checks.push({
      step: `5b. Buying power (${acctLabel})`,
      pass: bp != null && bp >= brokerMargin,
      detail: `optionBP=$${bp ?? 'null'}, need $${brokerMargin}/contract`,
    })

    // 5c: Capital percentage
    let capitalPct = 100
    try {
      capitalPct = await getCapitalPctForAccount(acct.name, acct.type)
    } catch (err: unknown) {
      checks.push({
        step: `5c. capital_pct (${acctLabel})`,
        pass: false,
        detail: `FAILED: ${err instanceof Error ? err.message : String(err)} — production account will be SKIPPED`,
      })
      continue
    }
    checks.push({
      step: `5c. capital_pct (${acctLabel})`,
      pass: capitalPct > 0,
      detail: `capital_pct=${capitalPct}%`,
    })

    // 5d: Simulate sizing (production uses its own pool, not shared with sandbox)
    const sameTypeCount = eligibleAccounts.filter(a => a.type === acct.type).length
    const botShare = sameTypeCount > 1 ? 1.0 / sameTypeCount : 1.0
    const usableBP = (bp ?? 0) * (capitalPct / 100) * botShare * 0.85
    const bpContracts = Math.floor(usableBP / brokerMargin)
    checks.push({
      step: `5d. Contract sizing (${acctLabel})`,
      pass: bpContracts >= 1,
      detail: `BP=$${bp}, capital_pct=${capitalPct}%, botShare=${(botShare * 100).toFixed(0)}% ` +
        `(${sameTypeCount} ${acct.type} accounts), usableBP=$${usableBP.toFixed(0)}, ` +
        `contracts=${bpContracts} (need ≥1)`,
    })
  }

  // Step 6: Check if stale positions would block
  let staleCount = 0
  try {
    const { getSandboxAccountPositions } = await import('@/lib/tradier')
    for (const acct of sandboxAccounts) {
      const positions = await getSandboxAccountPositions(acct.apiKey)
      const todayStr = new Date().toISOString().slice(0, 10)
      for (const p of positions) {
        if (!p.symbol || p.symbol.length < 15 || p.quantity === 0) continue
        try {
          const datePart = p.symbol.slice(3, 9)
          const expDate = `20${datePart.slice(0, 2)}-${datePart.slice(2, 4)}-${datePart.slice(4, 6)}`
          if (expDate <= todayStr) staleCount++
        } catch { /* ignore */ }
      }
    }
  } catch { /* ignore */ }
  checks.push({
    step: '6. Stale sandbox positions',
    pass: staleCount === 0,
    detail: staleCount === 0
      ? 'No stale positions in sandbox accounts'
      : `${staleCount} stale legs across sandbox accounts — would BLOCK all orders (including production) until cleaned`,
  })

  const failedChecks = checks.filter(c => !c.pass)
  const verdict = failedChecks.length === 0
    ? 'ALL CLEAR — production should place orders on next scan'
    : `BLOCKED at: ${failedChecks.map(c => c.step).join(', ')}`

  return NextResponse.json({ checks, verdict })
}
