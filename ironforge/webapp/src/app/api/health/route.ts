import { NextResponse } from 'next/server'
import { dbQuery } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

/**
 * GET /api/health
 *
 * Health check endpoint. Queries Databricks to verify connectivity.
 */
export async function GET() {
  try {
    const rows = await dbQuery('SELECT CURRENT_TIMESTAMP() as ts')
    return NextResponse.json({
      status: 'ok',
      time: rows[0]?.ts,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json(
      { status: 'error', message: msg },
      { status: 500 },
    )
  }
}
