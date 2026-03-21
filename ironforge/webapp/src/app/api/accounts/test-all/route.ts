import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'

interface TestResult {
  account_id: string
  person: string
  success: boolean
  message: string
  /** Discovered account number from Tradier profile */
  tradier_account_number?: string
  /** Total account equity (cash + positions) */
  total_equity?: number
  /** Option buying power (real collateral limit) */
  option_buying_power?: number
  /** Stock buying power (2x margin) */
  stock_buying_power?: number
  /** Account type from Tradier (margin, cash, pdt) */
  account_type?: string
  /** Number of open positions */
  open_positions?: number
  /** Day P&L (close_pl from Tradier) */
  day_pnl?: number
}

async function sandboxFetch(
  endpoint: string,
  apiKey: string,
): Promise<any> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)

  try {
    const res = await fetch(`${SANDBOX_URL}${endpoint}`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
      },
      cache: 'no-store',
      signal: controller.signal,
    })
    clearTimeout(timeout)
    if (!res.ok) return null
    return res.json()
  } catch {
    clearTimeout(timeout)
    return null
  }
}

async function testOne(
  accountId: string,
  apiKey: string,
  person: string,
): Promise<TestResult> {
  const fail = (msg: string): TestResult => ({
    account_id: accountId,
    person,
    success: false,
    message: msg,
  })

  // Step 1: Discover account number from profile
  const profileData = await sandboxFetch('/user/profile', apiKey)
  if (!profileData) return fail('Cannot reach Tradier sandbox API')

  let account = profileData.profile?.account
  if (Array.isArray(account)) account = account[0]
  const tradierAccountNumber = account?.account_number?.toString()

  if (!tradierAccountNumber) return fail('Connected but no account found in profile')

  // Step 2: Fetch balances and positions in parallel
  const [balData, posData] = await Promise.all([
    sandboxFetch(`/accounts/${tradierAccountNumber}/balances`, apiKey),
    sandboxFetch(`/accounts/${tradierAccountNumber}/positions`, apiKey),
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

  // Count open positions
  let openPositions = 0
  if (posData?.positions?.position) {
    const posList = Array.isArray(posData.positions.position)
      ? posData.positions.position
      : [posData.positions.position]
    openPositions = posList.length
  }

  return {
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
  }
}

/**
 * POST /api/accounts/test-all
 * Tests all active accounts by reading real API keys from the DB
 * and hitting Tradier sandbox to verify connection + fetch balances.
 */
export async function POST(_req: NextRequest) {
  try {
    const rows = await dbQuery(`
      SELECT account_id, api_key, person
      FROM ${TABLE}
      WHERE is_active = TRUE
      ORDER BY person
    `)

    const results = await Promise.all(
      rows.map((row) => testOne(row.account_id, row.api_key, row.person)),
    )

    return NextResponse.json(results)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
