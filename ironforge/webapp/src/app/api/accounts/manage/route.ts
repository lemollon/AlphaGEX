import { NextRequest, NextResponse } from 'next/server'
import { databricksFetch } from '@/lib/databricks-api'

export const dynamic = 'force-dynamic'

/** GET /api/accounts/manage — proxy to Databricks GET /api/accounts */
export async function GET() {
  try {
    const data = await databricksFetch('/api/accounts')
    return NextResponse.json(data)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

/** POST /api/accounts/manage — proxy to Databricks POST /api/accounts */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const data = await databricksFetch('/api/accounts', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    return NextResponse.json(data)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    const status = msg.includes('409') ? 409 : msg.includes('400') ? 400 : 500
    return NextResponse.json({ error: msg }, { status })
  }
}
