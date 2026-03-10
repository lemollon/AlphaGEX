import { NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

const SANDBOX_URL = 'https://sandbox.tradier.com/v1'

/** POST /api/accounts/test — test a single Tradier sandbox account connectivity */
export async function POST(req: NextRequest) {
  try {
    const { account_id, api_key } = await req.json()

    if (!account_id || !api_key) {
      return NextResponse.json(
        { error: 'account_id and api_key are required' },
        { status: 400 },
      )
    }

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 5000)

    try {
      const res = await fetch(`${SANDBOX_URL}/user/profile`, {
        headers: {
          Authorization: `Bearer ${api_key}`,
          Accept: 'application/json',
        },
        signal: controller.signal,
      })
      clearTimeout(timeout)

      if (res.ok) {
        return NextResponse.json({
          account_id,
          success: true,
          message: 'Connected',
        })
      }
      return NextResponse.json({
        account_id,
        success: false,
        message: `HTTP ${res.status}`,
      })
    } catch (fetchErr: unknown) {
      clearTimeout(timeout)
      const msg = fetchErr instanceof Error && fetchErr.name === 'AbortError'
        ? 'Timeout'
        : fetchErr instanceof Error ? fetchErr.message : 'Unknown error'
      return NextResponse.json({ account_id, success: false, message: msg })
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
