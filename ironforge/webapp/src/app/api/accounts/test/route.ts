import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const SANDBOX_URL = 'https://sandbox.tradier.com/v1'
const PRODUCTION_URL = 'https://api.tradier.com/v1'

/**
 * POST /api/accounts/test — test a single Tradier account connectivity + fetch balance data
 * Body: { account_id, api_key, type? }
 * type defaults to 'sandbox'. Pass 'production' for production API keys.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { account_id, api_key, type } = body
    const accountType = type === 'production' ? 'production' : 'sandbox'
    const baseUrl = accountType === 'production' ? PRODUCTION_URL : SANDBOX_URL
    const label = accountType === 'production' ? 'Tradier production API' : 'Tradier sandbox API'

    if (!account_id || !api_key) {
      return NextResponse.json(
        { error: 'account_id and api_key are required' },
        { status: 400 },
      )
    }

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)

    try {
      // Step 1: Verify API key via profile
      const profileRes = await fetch(`${baseUrl}/user/profile`, {
        headers: {
          Authorization: `Bearer ${api_key}`,
          Accept: 'application/json',
        },
        signal: controller.signal,
      })
      clearTimeout(timeout)

      if (!profileRes.ok) {
        console.warn(`[accounts/test] ${label} returned HTTP ${profileRes.status} for account ${account_id}`)
        return NextResponse.json({
          account_id,
          success: false,
          message: `${label}: HTTP ${profileRes.status}`,
        })
      }

      const profileData = await profileRes.json()
      let account = profileData.profile?.account
      if (Array.isArray(account)) account = account[0]
      const tradierAccountNumber = account?.account_number?.toString()

      if (!tradierAccountNumber) {
        return NextResponse.json({
          account_id,
          success: true,
          message: 'Connected but no account found in profile',
        })
      }

      // Step 2: Fetch balances and positions
      const fetchJson = async (endpoint: string) => {
        try {
          const r = await fetch(`${baseUrl}${endpoint}`, {
            headers: { Authorization: `Bearer ${api_key}`, Accept: 'application/json' },
            signal: AbortSignal.timeout(5000),
          })
          return r.ok ? r.json() : null
        } catch { return null }
      }

      const [balData, posData] = await Promise.all([
        fetchJson(`/accounts/${tradierAccountNumber}/balances`),
        fetchJson(`/accounts/${tradierAccountNumber}/positions`),
      ])

      const bal = balData?.balances || {}
      const pdt = bal.pdt || {}
      const margin = bal.margin || {}

      const totalEquity = bal.total_equity != null ? parseFloat(bal.total_equity) : null
      const optionBp =
        margin.option_buying_power != null ? parseFloat(margin.option_buying_power) :
        pdt.option_buying_power != null ? parseFloat(pdt.option_buying_power) :
        null
      const accountTypeTradier = bal.account_type || null
      const dayPnl = bal.close_pl != null ? parseFloat(bal.close_pl) : null

      let openPositions = 0
      if (posData?.positions?.position) {
        const posList = Array.isArray(posData.positions.position)
          ? posData.positions.position
          : [posData.positions.position]
        openPositions = posList.length
      }

      return NextResponse.json({
        account_id,
        success: true,
        message: 'Connected',
        tradier_account_number: tradierAccountNumber,
        total_equity: totalEquity,
        option_buying_power: optionBp,
        account_type: accountTypeTradier,
        open_positions: openPositions,
        day_pnl: dayPnl,
      })
    } catch (fetchErr: unknown) {
      clearTimeout(timeout)
      const msg = fetchErr instanceof Error && fetchErr.name === 'AbortError'
        ? 'Timeout'
        : fetchErr instanceof Error ? fetchErr.message : 'Unknown error'
      console.warn(`[accounts/test] Account ${account_id} test failed: ${msg}`)
      return NextResponse.json({ account_id, success: false, message: msg })
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
