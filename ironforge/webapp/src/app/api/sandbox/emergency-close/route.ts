import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, escapeSql, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'
export const maxDuration = 120 // Allow up to 2 minutes for this endpoint

const SANDBOX_URL = 'https://sandbox.tradier.com/v1'

interface SandboxAccount {
  name: string
  apiKey: string
}

function getSandboxAccounts(): SandboxAccount[] {
  const accounts: SandboxAccount[] = []
  const userKey = process.env.TRADIER_SANDBOX_KEY_USER || ''
  const mattKey = process.env.TRADIER_SANDBOX_KEY_MATT || ''
  const loganKey = process.env.TRADIER_SANDBOX_KEY_LOGAN || ''
  if (userKey) accounts.push({ name: 'User', apiKey: userKey })
  if (mattKey) accounts.push({ name: 'Matt', apiKey: mattKey })
  if (loganKey) accounts.push({ name: 'Logan', apiKey: loganKey })
  return accounts
}

const _accountIdCache: Record<string, string> = {}

async function getAccountId(apiKey: string): Promise<string | null> {
  if (_accountIdCache[apiKey]) return _accountIdCache[apiKey]
  try {
    const res = await fetch(`${SANDBOX_URL}/user/profile`, {
      headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!res.ok) return null
    const data = await res.json()
    let account = data.profile?.account
    if (Array.isArray(account)) account = account[0]
    const id = account?.account_number?.toString()
    if (id) _accountIdCache[apiKey] = id
    return id || null
  } catch { return null }
}

async function sandboxGet(endpoint: string, apiKey: string): Promise<any> {
  try {
    const res = await fetch(`${SANDBOX_URL}${endpoint}`, {
      headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!res.ok) return null
    return res.json()
  } catch { return null }
}

async function sandboxPost(endpoint: string, body: Record<string, string>, apiKey: string): Promise<any> {
  try {
    const res = await fetch(`${SANDBOX_URL}${endpoint}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams(body).toString(),
      cache: 'no-store',
    })
    if (!res.ok) return null
    return res.json()
  } catch { return null }
}

interface PositionCloseResult {
  symbol: string
  quantity: number
  status: 'closed' | 'failed' | 'expired_skip'
  method?: string
  error?: string
}

interface AccountResult {
  name: string
  account_id: string | null
  positions_found: number
  positions_closed: number
  positions_failed: number
  buying_power_before: number | null
  buying_power_after: number | null
  details: PositionCloseResult[]
}

/**
 * GET /api/sandbox/emergency-close
 *
 * Read-only diagnostic: shows all sandbox positions across all accounts
 * with buying power status. Safe to call anytime.
 */
export async function GET(): Promise<NextResponse> {
  const accounts = getSandboxAccounts()
  if (accounts.length === 0) {
    return NextResponse.json({ error: 'No sandbox accounts configured' }, { status: 400 })
  }

  const results: Array<{
    name: string
    account_id: string | null
    buying_power: number | null
    positions: any[]
  }> = []

  await Promise.all(
    accounts.map(async (acct) => {
      const accountId = await getAccountId(acct.apiKey)
      if (!accountId) {
        results.push({ name: acct.name, account_id: null, buying_power: null, positions: [] })
        return
      }

      const [balData, posData] = await Promise.all([
        sandboxGet(`/accounts/${accountId}/balances`, acct.apiKey),
        sandboxGet(`/accounts/${accountId}/positions`, acct.apiKey),
      ])

      // Tradier nests buying power differently for margin/PDT/cash accounts
      const bal = balData?.balances || {}
      const pdt = bal.pdt || {}
      const margin = bal.margin || {}
      const bp =
        pdt.option_buying_power ?? margin.option_buying_power ??
        bal.option_buying_power ?? pdt.stock_buying_power ??
        margin.stock_buying_power ?? bal.buying_power ?? bal.total_cash
      let positions = posData?.positions?.position
      if (!positions) positions = []
      if (!Array.isArray(positions)) positions = [positions]

      results.push({
        name: acct.name,
        account_id: accountId,
        buying_power: bp != null ? parseFloat(bp) : null,
        positions: positions.map((p: any) => ({
          symbol: p.symbol,
          quantity: parseFloat(p.quantity || '0'),
          cost_basis: parseFloat(p.cost_basis || '0'),
          date_acquired: p.date_acquired,
        })),
      })
    }),
  )

  return NextResponse.json({
    accounts: results,
    total_positions: results.reduce((s, a) => s + a.positions.length, 0),
    any_negative_bp: results.some((a) => a.buying_power != null && a.buying_power < 0),
  })
}

/**
 * POST /api/sandbox/emergency-close
 *
 * KILL SWITCH: Force-close ALL open positions in ALL sandbox accounts.
 * No time gates. No market hours check. Uses cascade close strategy.
 *
 * Also force-closes all open paper positions in the DB and reconciles balances.
 *
 * Body (optional): { "paper_only": true } to skip sandbox API calls and only close DB positions.
 */
export async function POST(req: NextRequest): Promise<NextResponse> {
  const accounts = getSandboxAccounts()
  if (accounts.length === 0) {
    return NextResponse.json({ error: 'No sandbox accounts configured' }, { status: 400 })
  }

  let paperOnly = false
  try {
    const body = await req.json()
    paperOnly = !!body?.paper_only
  } catch { /* no body is fine */ }

  const accountResults: AccountResult[] = []

  // --- Phase 1: Close all sandbox positions via Tradier API ---
  if (!paperOnly) {
    await Promise.all(
      accounts.map(async (acct) => {
        const accountId = await getAccountId(acct.apiKey)
        if (!accountId) {
          accountResults.push({
            name: acct.name, account_id: null,
            positions_found: 0, positions_closed: 0, positions_failed: 0,
            buying_power_before: null, buying_power_after: null, details: [],
          })
          return
        }

        // Get current buying power (Tradier nests under margin/pdt for non-cash accounts)
        const balBefore = await sandboxGet(`/accounts/${accountId}/balances`, acct.apiKey)
        const balB = balBefore?.balances || {}
        const pdtB = balB.pdt || {}; const marginB = balB.margin || {}
        const bpBefore = pdtB.option_buying_power ?? marginB.option_buying_power ??
          balB.option_buying_power ?? marginB.stock_buying_power ?? balB.buying_power ?? balB.total_cash
        const bpBeforeNum = bpBefore != null ? parseFloat(bpBefore) : null

        // Get all positions
        const posData = await sandboxGet(`/accounts/${accountId}/positions`, acct.apiKey)
        let positions = posData?.positions?.position
        if (!positions) positions = []
        if (!Array.isArray(positions)) positions = [positions]

        const details: PositionCloseResult[] = []

        for (const pos of positions) {
          const symbol = pos.symbol || ''
          const quantity = Math.abs(parseFloat(pos.quantity || '0'))
          if (quantity === 0) continue

          const side = parseFloat(pos.quantity || '0') < 0 ? 'buy_to_close' : 'sell_to_close'

          // Try individual leg close (most reliable for emergency)
          const legBody: Record<string, string> = {
            class: 'option',
            symbol: symbol.slice(0, 3), // Ticker from OCC (SPY)
            option_symbol: symbol,
            side,
            quantity: String(Math.round(quantity)),
            type: 'market',
            duration: 'day',
          }

          const result = await sandboxPost(`/accounts/${accountId}/orders`, legBody, acct.apiKey)
          if (result?.order?.id) {
            details.push({ symbol, quantity, status: 'closed', method: 'market_order' })
          } else {
            // Try penny close ($0.01) for expired/worthless options
            const pennyBody: Record<string, string> = {
              ...legBody,
              type: 'limit',
              price: '0.01',
            }
            const pennyResult = await sandboxPost(`/accounts/${accountId}/orders`, pennyBody, acct.apiKey)
            if (pennyResult?.order?.id) {
              details.push({ symbol, quantity, status: 'closed', method: 'penny_close' })
            } else {
              details.push({
                symbol, quantity, status: 'failed',
                error: 'Market and penny close both rejected (options may have expired — wait for settlement)',
              })
            }
          }
        }

        // Re-check buying power after closes
        const balAfter = await sandboxGet(`/accounts/${accountId}/balances`, acct.apiKey)
        const balA = balAfter?.balances || {}
        const pdtA = balA.pdt || {}; const marginA = balA.margin || {}
        const bpAfter = pdtA.option_buying_power ?? marginA.option_buying_power ??
          balA.option_buying_power ?? marginA.stock_buying_power ?? balA.buying_power ?? balA.total_cash
        const bpAfterNum = bpAfter != null ? parseFloat(bpAfter) : null

        accountResults.push({
          name: acct.name,
          account_id: accountId,
          positions_found: positions.length,
          positions_closed: details.filter((d) => d.status === 'closed').length,
          positions_failed: details.filter((d) => d.status === 'failed').length,
          buying_power_before: bpBeforeNum,
          buying_power_after: bpAfterNum,
          details,
        })
      }),
    )
  }

  // --- Phase 2: Force-close ALL open paper positions in DB ---
  const paperResults: Array<{ bot: string; dte: string; positions_closed: number }> = []
  for (const bot of ['flame', 'spark', 'inferno']) {
    const dte = dteMode(bot) || ''

    // Find all open positions
    const openPositions = await dbQuery(
      `SELECT position_id, total_credit, contracts, collateral_required
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = '${escapeSql(dte)}'`,
    )

    if (openPositions.length === 0) {
      paperResults.push({ bot, dte, positions_closed: 0 })
      continue
    }

    // Close each position at entry credit (P&L = $0 for emergency close)
    let actualClosed = 0
    for (const pos of openPositions) {
      const credit = num(pos.total_credit)
      const rowsAffected = await dbExecute(
        `UPDATE ${botTable(bot, 'positions')}
         SET status = 'closed', close_time = NOW(),
             close_price = ${credit}, realized_pnl = 0,
             close_reason = 'emergency_kill_switch', updated_at = NOW()
         WHERE position_id = '${escapeSql(pos.position_id)}' AND status = 'open'
           AND dte_mode = '${escapeSql(dte)}'`,
      )
      if (rowsAffected === 0) continue // Already closed by scanner — skip
      actualClosed++
    }

    // Reconcile paper_account
    const pnlRows = await dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) as total_pnl, COUNT(*) as total_trades
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
         AND dte_mode = '${escapeSql(dte)}'`,
    )
    const actualPnl = num(pnlRows[0]?.total_pnl)
    const actualTrades = Math.round(num(pnlRows[0]?.total_trades))
    const balance = Math.round((10000 + actualPnl) * 100) / 100

    await dbExecute(
      `UPDATE ${botTable(bot, 'paper_account')}
       SET current_balance = ${balance},
           cumulative_pnl = ${actualPnl},
           collateral_in_use = 0,
           buying_power = ${balance},
           total_trades = ${actualTrades},
           updated_at = NOW()
       WHERE dte_mode = '${escapeSql(dte)}'`,
    )

    // Log the emergency action
    await dbExecute(
      `INSERT INTO ${botTable(bot, 'logs')} (log_time, level, message, details, dte_mode)
       VALUES (NOW(), 'RECOVERY',
               '${escapeSql(`EMERGENCY KILL SWITCH: ${openPositions.length} positions force-closed`)}',
               '${escapeSql(JSON.stringify({ positions_closed: openPositions.length, source: 'emergency_kill_switch', paper_only: paperOnly }))}',
               '${escapeSql(dte)}')`,
    )

    paperResults.push({ bot, dte, positions_closed: actualClosed })
  }

  const totalSandboxClosed = accountResults.reduce((s, a) => s + a.positions_closed, 0)
  const totalSandboxFailed = accountResults.reduce((s, a) => s + a.positions_failed, 0)
  const totalPaperClosed = paperResults.reduce((s, p) => s + p.positions_closed, 0)
  const anyNegativeBP = accountResults.some((a) => a.buying_power_after != null && a.buying_power_after < 0)

  return NextResponse.json({
    sandbox_results: accountResults,
    paper_results: paperResults,
    summary: {
      sandbox_positions_closed: totalSandboxClosed,
      sandbox_positions_failed: totalSandboxFailed,
      paper_positions_closed: totalPaperClosed,
      any_negative_bp_remaining: anyNegativeBP,
      recommendation: anyNegativeBP
        ? 'Sandbox buying power still negative. Expired options may need overnight settlement. Consider switching FLAME to paper-only mode.'
        : totalSandboxFailed > 0
          ? 'Some sandbox positions could not be closed (likely expired). Wait for overnight settlement.'
          : 'All positions closed successfully.',
    },
  })
}
