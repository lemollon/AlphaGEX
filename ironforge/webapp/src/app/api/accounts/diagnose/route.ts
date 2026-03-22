import { NextResponse } from 'next/server'
import { dbQuery, sharedTable } from '@/lib/db'

export const dynamic = 'force-dynamic'

const TABLE = sharedTable('ironforge_accounts')
const SANDBOX_URL = 'https://sandbox.tradier.com/v1'
const PRODUCTION_URL = 'https://api.tradier.com/v1'

function mask(key: string): string {
  if (!key || key.length < 9) return '****'
  return `${key.slice(0, 4)}...${key.slice(-4)}`
}

/**
 * GET /api/accounts/diagnose
 *
 * Step-by-step diagnostic for ALL accounts — shows exactly where
 * each fetch step succeeds or fails. Paste this URL into your browser.
 */
export async function GET() {
  const results: any[] = []

  try {
    const rows = await dbQuery(`
      SELECT id, person, account_id, api_key, type
      FROM ${TABLE}
      WHERE is_active = TRUE
      ORDER BY type, person
    `)

    for (const row of rows) {
      const acctType = row.type || 'sandbox'
      const baseUrl = acctType === 'production' ? PRODUCTION_URL : SANDBOX_URL
      const diag: any = {
        id: row.id,
        person: row.person,
        stored_account_id: row.account_id,
        type: acctType,
        api_key_masked: mask(row.api_key || ''),
        base_url: baseUrl,
        steps: {},
      }

      // Step 1: Profile discovery
      try {
        const t0 = Date.now()
        const profileRes = await fetch(`${baseUrl}/user/profile`, {
          headers: { Authorization: `Bearer ${row.api_key}`, Accept: 'application/json' },
          cache: 'no-store',
          signal: AbortSignal.timeout(8000),
        })
        const profileMs = Date.now() - t0

        if (!profileRes.ok) {
          const errBody = await profileRes.text().catch(() => '')
          diag.steps.profile = {
            success: false,
            http_status: profileRes.status,
            ms: profileMs,
            error_body: errBody.slice(0, 200),
          }
          results.push(diag)
          continue
        }

        const profileData = await profileRes.json()
        let account = profileData.profile?.account
        if (Array.isArray(account)) account = account[0]
        const discoveredId = account?.account_number?.toString()

        diag.steps.profile = {
          success: true,
          http_status: 200,
          ms: profileMs,
          discovered_account_id: discoveredId || null,
          account_keys: account ? Object.keys(account) : [],
        }

        const realId = discoveredId || row.account_id

        // Step 2: Balance fetch
        try {
          const t1 = Date.now()
          const balRes = await fetch(`${baseUrl}/accounts/${realId}/balances`, {
            headers: { Authorization: `Bearer ${row.api_key}`, Accept: 'application/json' },
            cache: 'no-store',
            signal: AbortSignal.timeout(8000),
          })
          const balMs = Date.now() - t1

          if (!balRes.ok) {
            const errBody = await balRes.text().catch(() => '')
            diag.steps.balances = {
              success: false,
              http_status: balRes.status,
              ms: balMs,
              url_used: `${baseUrl}/accounts/${realId}/balances`,
              error_body: errBody.slice(0, 300),
            }
          } else {
            const balData = await balRes.json()
            const bal = balData?.balances || {}
            const margin = bal.margin || {}
            const pdt = bal.pdt || {}
            diag.steps.balances = {
              success: true,
              http_status: 200,
              ms: balMs,
              url_used: `${baseUrl}/accounts/${realId}/balances`,
              total_equity: bal.total_equity ?? null,
              account_type: bal.account_type ?? null,
              margin_obp: margin.option_buying_power ?? null,
              pdt_obp: pdt.option_buying_power ?? null,
              close_pl: bal.close_pl ?? null,
              top_level_keys: Object.keys(bal),
            }
          }
        } catch (balErr: unknown) {
          const msg = balErr instanceof Error ? balErr.message : String(balErr)
          diag.steps.balances = { success: false, error: msg }
        }

        // Step 3: Positions fetch
        try {
          const t2 = Date.now()
          const posRes = await fetch(`${baseUrl}/accounts/${realId}/positions`, {
            headers: { Authorization: `Bearer ${row.api_key}`, Accept: 'application/json' },
            cache: 'no-store',
            signal: AbortSignal.timeout(8000),
          })
          const posMs = Date.now() - t2

          if (!posRes.ok) {
            const errBody = await posRes.text().catch(() => '')
            diag.steps.positions = {
              success: false,
              http_status: posRes.status,
              ms: posMs,
              error_body: errBody.slice(0, 200),
            }
          } else {
            const posData = await posRes.json()
            let count = 0
            if (posData?.positions?.position) {
              const pl = Array.isArray(posData.positions.position)
                ? posData.positions.position
                : [posData.positions.position]
              count = pl.length
            }
            diag.steps.positions = {
              success: true,
              http_status: 200,
              ms: posMs,
              open_positions: count,
            }
          }
        } catch (posErr: unknown) {
          const msg = posErr instanceof Error ? posErr.message : String(posErr)
          diag.steps.positions = { success: false, error: msg }
        }
      } catch (profileErr: unknown) {
        const msg = profileErr instanceof Error ? profileErr.message : String(profileErr)
        diag.steps.profile = { success: false, error: msg }
      }

      results.push(diag)
    }

    return NextResponse.json({
      timestamp: new Date().toISOString(),
      total_accounts: rows.length,
      results,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
