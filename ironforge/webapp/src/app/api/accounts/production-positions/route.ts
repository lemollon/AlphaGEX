import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export const dynamic = 'force-dynamic'

const PRODUCTION_URL = 'https://api.tradier.com/v1'

/**
 * GET /api/accounts/production-positions
 *
 * Checks all Iron Viper production Tradier accounts for open positions.
 * Returns raw Tradier position data so you can see exactly what's open.
 */
export async function GET() {
  try {
    // Load production accounts from DB
    const accounts = await query(
      `SELECT id, person, account_id, api_key, bot, capital_pct
       FROM ironforge_accounts
       WHERE type = 'production' AND is_active = TRUE
       ORDER BY person`,
    )

    if (accounts.length === 0) {
      return NextResponse.json({
        message: 'No active production accounts found',
        accounts: [],
      })
    }

    const results = await Promise.all(
      accounts.map(async (acct) => {
        const apiKey = acct.api_key?.trim()
        if (!apiKey) {
          return {
            person: acct.person,
            account_id: acct.account_id,
            bot: acct.bot,
            error: 'No API key',
            positions: [],
            has_open_positions: false,
          }
        }

        // Discover account ID if not stored
        let accountId = acct.account_id?.trim()
        if (!accountId) {
          try {
            const profileRes = await fetch(`${PRODUCTION_URL}/user/profile`, {
              headers: {
                Authorization: `Bearer ${apiKey}`,
                Accept: 'application/json',
              },
              cache: 'no-store',
            })
            if (profileRes.ok) {
              const profileData = await profileRes.json()
              const acctData = profileData?.profile?.account
              if (acctData) {
                accountId = Array.isArray(acctData)
                  ? acctData[0]?.account_number
                  : acctData.account_number
              }
            }
          } catch {
            // ignore
          }
          if (!accountId) {
            return {
              person: acct.person,
              account_id: null,
              bot: acct.bot,
              error: 'Could not discover account ID',
              positions: [],
              has_open_positions: false,
            }
          }
        }

        // Fetch positions from Tradier production
        let positions: any[] = []
        let balanceData: any = null
        let error: string | null = null

        try {
          const [posRes, balRes] = await Promise.all([
            fetch(`${PRODUCTION_URL}/accounts/${accountId}/positions`, {
              headers: {
                Authorization: `Bearer ${apiKey}`,
                Accept: 'application/json',
              },
              cache: 'no-store',
            }),
            fetch(`${PRODUCTION_URL}/accounts/${accountId}/balances`, {
              headers: {
                Authorization: `Bearer ${apiKey}`,
                Accept: 'application/json',
              },
              cache: 'no-store',
            }),
          ])

          if (posRes.ok) {
            const posData = await posRes.json()
            if (posData?.positions?.position) {
              positions = Array.isArray(posData.positions.position)
                ? posData.positions.position
                : [posData.positions.position]
            }
          } else {
            error = `Positions API returned ${posRes.status}`
          }

          if (balRes.ok) {
            const bd = await balRes.json()
            balanceData = bd?.balances || null
          }
        } catch (e: unknown) {
          error = e instanceof Error ? e.message : String(e)
        }

        // Group positions into IC spreads by expiration
        const byExpiration: Record<string, any[]> = {}
        for (const pos of positions) {
          const sym = pos.symbol || ''
          // OCC format: SPY260323C00585000
          const expMatch = sym.match(/^[A-Z]+(\d{6})[CP]/)
          const expKey = expMatch ? expMatch[1] : 'unknown'
          if (!byExpiration[expKey]) byExpiration[expKey] = []
          byExpiration[expKey].push({
            symbol: pos.symbol,
            quantity: pos.quantity,
            cost_basis: pos.cost_basis,
            date_acquired: pos.date_acquired,
          })
        }

        return {
          person: acct.person,
          account_id: accountId,
          bot: acct.bot,
          capital_pct: acct.capital_pct,
          error,
          balance: balanceData
            ? {
                total_equity: balanceData.total_equity,
                option_buying_power: balanceData.option_buying_power,
                day_pnl: balanceData.close_pl,
                pending_orders_count: balanceData.pending_orders_count,
              }
            : null,
          has_open_positions: positions.length > 0,
          position_count: positions.length,
          ic_count: positions.length > 0 ? Math.ceil(positions.length / 4) : 0,
          positions_by_expiration: byExpiration,
          raw_positions: positions,
        }
      }),
    )

    const anyOpen = results.some((r) => r.has_open_positions)

    return NextResponse.json({
      checked_at: new Date().toISOString(),
      any_open_positions: anyOpen,
      total_production_accounts: results.length,
      summary: anyOpen
        ? `⚠️ OPEN POSITIONS FOUND in production`
        : `✅ No open positions in any production account`,
      accounts: results,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
