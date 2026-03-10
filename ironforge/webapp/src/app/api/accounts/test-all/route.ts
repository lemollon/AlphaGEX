import { NextRequest, NextResponse } from 'next/server'
import { databricksFetch } from '@/lib/databricks-api'

export const dynamic = 'force-dynamic'

/** POST /api/accounts/test-all — proxy to Databricks POST /api/accounts/test-all */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const data = await databricksFetch('/api/accounts/test-all', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    return NextResponse.json(data)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
