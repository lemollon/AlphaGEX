import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'
const PRODUCTION_URL = 'https://api.tradier.com/v1'

async function tradierFetch(
  endpoint: string,
  apiKey: string,
  baseUrl: string,
): Promise<any> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)

  try {
    const res = await fetch(`${baseUrl}${endpoint}`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
      },
      cache: 'no-store',
      signal: controller.signal,
    })
    clearTimeout(timeout)
    if (!res.ok) {
      console.warn(`[accounts/test] Tradier ${endpoint} returned HTTP ${res.status}`)
      return null
    }
    return res.json()
  } catch (err: unknown) {
    clearTimeout(timeout)
    const msg = err instanceof Error
      ? (err.name === 'AbortError' ? 'timeout (5s)' : err.message)
      : 'unknown error'
    console.warn(`[accounts/test] Tradier ${endpoint} failed: ${msg}`)
    return null
  }
}

/**
 * POST /api/accounts/manage/:id/test
 * Tests a single account by reading its API key from the DB
 * and hitting the correct Tradier API (sandbox or production).
 */
export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const id = parseInt(params.id)
    if (isNaN(id)) {
      return NextResponse.json({ error: 'Invalid ID' }, { status: 400 })
    }

    const rows = await dbQuery(
      `SELECT account_id, api_key, person, type
       FROM ${TABLE}
       WHERE id = $1 LIMIT 1`,
      [id],
    )
    if (rows.length === 0) {
      return NextResponse.json({ error: 'Account not found' }, { status: 404 })
    }

    const row = rows[0]
    const accountId = row.account_id
    const apiKey = row.api_key
    const person = row.person
    const type = row.type || 'sandbox'
    const baseUrl = type === 'production' ? PRODUCTION_URL : SANDBOX_URL
    const label = type === 'production' ? 'Tradier production API' : 'Tradier sandbox API'

    // Step 1: Discover account number from profile
    const profileData = await tradierFetch('/user/profile', apiKey, baseUrl)
    if (!profileData) {
      return NextResponse.json({
        account_id: accountId,
        person,
        success: false,
        message: `Cannot reach ${label}`,
      })
    }

    let account = profileData.profile?.account
    if (Array.isArray(account)) account = account[0]
    const tradierAccountNumber = account?.account_number?.toString()

    if (!tradierAccountNumber) {
      return NextResponse.json({
        account_id: accountId,
        person,
        success: false,
        message: 'Connected but no account found in profile',
      })
    }

    // Step 2: Fetch balances and positions in parallel
    const [balData, posData] = await Promise.all([
      tradierFetch(`/accounts/${tradierAccountNumber}/balances`, apiKey, baseUrl),
      tradierFetch(`/accounts/${tradierAccountNumber}/positions`, apiKey, baseUrl),
    ])

    const bal = balData?.balances || {}
    const pdt = bal.pdt || {}
    const margin = bal.margin || {}

    const totalEquity = bal.total_equity != null ? parseFloat(bal.total_equity) : undefined
    const optionBp =
      margin.option_buying_power != null ? parseFloat(margin.option_buying_power) :
      pdt.option_buying_power != null ? parseFloat(pdt.option_buying_power) :
      undefined
    const stockBp =
      margin.stock_buying_power != null ? parseFloat(margin.stock_buying_power) :
      pdt.stock_buying_power != null ? parseFloat(pdt.stock_buying_power) :
      undefined
    const accountType = bal.account_type || undefined
    const closePl = bal.close_pl != null ? parseFloat(bal.close_pl) : undefined

    let openPositions = 0
    if (posData?.positions?.position) {
      const posList = Array.isArray(posData.positions.position)
        ? posData.positions.position
        : [posData.positions.position]
      openPositions = posList.length
    }

    return NextResponse.json({
      account_id: accountId,
      person,
      success: true,
      message: 'Connected',
      tradier_account_number: tradierAccountNumber,
      total_equity: totalEquity,
      option_buying_power: optionBp,
      stock_buying_power: stockBp,
      account_type: accountType,
      open_positions: openPositions,
      day_pnl: closePl,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
