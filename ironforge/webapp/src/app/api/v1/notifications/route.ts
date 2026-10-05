import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Notification HISTORY feed (10.4 gap audit — the app.html notifications sheet and
 * dashboard bell both show a past-events feed, but only preferences/devices existed).
 * Rows are written from inside dispatchToCustomers (lib/push/dispatch.ts), the single
 * place every push category already funnels through — this route only reads them.
 *
 * Cursor-paginated, newest first: cursor is opaque base64 of `created_at_iso|id`, the
 * sort key of the last row on the previous page, same convention as GET /api/live/trades.
 * Unlike that route, the WHERE clause runs in SQL (a row-value comparison) rather than
 * an in-memory slice — this feed has no filters to pre-aggregate, so there is no reason
 * to pull the whole table into Node first.
 */
const DEFAULT_LIMIT = 20
const MAX_LIMIT = 50

interface NotificationRow {
  id: string
  kind: string
  title: string
  body: string
  data: unknown
  created_at: string
  read_at: string | null
}

function decodeCursor(raw: string | null): { createdAt: string; id: string } | null {
  if (!raw) return null
  try {
    const decoded = Buffer.from(raw, 'base64').toString('utf8')
    const sep = decoded.lastIndexOf('|')
    if (sep < 0) return null
    const createdAt = decoded.slice(0, sep)
    const id = decoded.slice(sep + 1)
    if (!createdAt || !id) return null
    return { createdAt, id }
  } catch {
    return null
  }
}

function encodeCursor(row: NotificationRow): string {
  return Buffer.from(`${row.created_at}|${row.id}`, 'utf8').toString('base64')
}

export async function GET(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, notifications: [], next_cursor: null, unread_count: 0 })
  }

  const sp = req.nextUrl.searchParams
  const limitParam = Number(sp.get('limit'))
  const limit = Number.isFinite(limitParam) && limitParam > 0 ? Math.min(limitParam, MAX_LIMIT) : DEFAULT_LIMIT
  const cursor = decodeCursor(sp.get('cursor'))

  const rows = await customerQuery<NotificationRow>(
    cursor
      ? `SELECT id, kind, title, body, data, created_at, read_at
           FROM customer_notifications
          WHERE user_id = $1
            AND (created_at, id) < ($2::timestamptz, $3::uuid)
          ORDER BY created_at DESC, id DESC
          LIMIT $4`
      : `SELECT id, kind, title, body, data, created_at, read_at
           FROM customer_notifications
          WHERE user_id = $1
          ORDER BY created_at DESC, id DESC
          LIMIT $2`,
    cursor
      ? [identity.customerId, cursor.createdAt, cursor.id, limit]
      : [identity.customerId, limit],
  )

  const [{ count }] = await customerQuery<{ count: string }>(
    `SELECT count(*)::text AS count FROM customer_notifications WHERE user_id = $1 AND read_at IS NULL`,
    [identity.customerId],
  )

  return NextResponse.json({
    ok: true,
    notifications: rows,
    next_cursor: rows.length === limit ? encodeCursor(rows[rows.length - 1]) : null,
    unread_count: Number(count ?? 0),
  })
}
