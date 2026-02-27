import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/health
 *
 * Health check endpoint. Queries the database (which triggers
 * ensureTables → scanner start on first call after boot).
 * Used by Render's healthCheckPath to keep the service alive
 * and guarantee the scanner starts immediately after deploy.
 */
export async function GET() {
  try {
    const rows = await query('SELECT NOW() as ts')
    return NextResponse.json({
      status: 'ok',
      time: rows[0]?.ts,
    })
  } catch (err: any) {
    return NextResponse.json(
      { status: 'error', message: err.message },
      { status: 500 },
    )
  }
}
