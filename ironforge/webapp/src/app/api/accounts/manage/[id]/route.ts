import { NextRequest, NextResponse } from 'next/server'
import { databricksFetch } from '@/lib/databricks-api'

export const dynamic = 'force-dynamic'

/** PUT /api/accounts/manage/:id — proxy to Databricks PUT /api/accounts/:id */
export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const body = await req.json()
    const data = await databricksFetch(`/api/accounts/${params.id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    })
    return NextResponse.json(data)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    const status = msg.includes('404') ? 404 : msg.includes('400') ? 400 : 500
    return NextResponse.json({ error: msg }, { status })
  }
}

/** DELETE /api/accounts/manage/:id — proxy to Databricks DELETE /api/accounts/:id */
export async function DELETE(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const data = await databricksFetch(`/api/accounts/${params.id}`, {
      method: 'DELETE',
    })
    return NextResponse.json(data)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    const status = msg.includes('404') ? 404 : 500
    return NextResponse.json({ error: msg }, { status })
  }
}
