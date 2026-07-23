import { NextRequest, NextResponse } from 'next/server'
import { lookupPromo } from '@/lib/promo'

export const dynamic = 'force-dynamic'

/**
 * Public promo-code validator. GET /api/public/promo?code=FORGE50
 *
 * Read-only, no session, no DB — just looks the code up in the static promo list
 * so the signup form can confirm a code live. Returns the offer terms on a hit.
 */
export async function GET(req: NextRequest) {
  const code = req.nextUrl.searchParams.get('code')
  const promo = lookupPromo(code)
  if (!promo) {
    return NextResponse.json({ valid: false }, { headers: { 'Cache-Control': 'no-store' } })
  }
  return NextResponse.json({ valid: true, promo }, {
    headers: { 'Cache-Control': 'public, max-age=300' },
  })
}
