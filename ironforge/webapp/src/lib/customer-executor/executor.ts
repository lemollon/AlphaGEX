/**
 * Customer order executor (Phase B) — mirrors SPARK/FLAME master position opens and
 * closes into activated customers' brokerage accounts via SnapTrade multi-leg orders
 * (tastytrade first; a Tradier adapter drops in when partner creds exist).
 *
 * SHIPS DISARMED: every OPEN is gated on CUSTOMER_EXECUTOR_ENABLED === 'true', which
 * is unset in production. Arming is a deliberate operator act after live-testing
 * against a real account (knob fail-safe invariant: no bot ships armed).
 *
 * Design invariants:
 *  - NEVER throws into the scanner. Every entry point catches everything; the master
 *    bot's own trading must be unaffected by any customer failure.
 *  - Durable idempotency: one row per (source_position_id, user_id) in
 *    customer_positions, claimed with INSERT … ON CONFLICT DO NOTHING before any
 *    broker call. Survives restarts, unlike the scanner's in-memory guards.
 *  - Opens FAIL CLOSED on every gate (see contracts.ts canOpenForCustomer). Closes are
 *    deliberately NOT gated by the arming flag / subscription / pause: an open customer
 *    position must always be closeable or a pause strands real risk.
 *  - Per-customer error isolation: one customer's failure never blocks another's order.
 *
 * Consent basis: enrollment v2 activation = standing authorization (TRADING_AUTH legal
 * doc + preview-hash consent + acknowledgments). The per-trade approval contract in
 * lib/brokerage/approval.ts continues to govern only the legacy v1 surface.
 */
import { customerQuery, customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { getSnapTrade, isSnapTradeConfigured } from '@/lib/snaptrade'
import { loadSnapTradeCreds } from '@/lib/brokerage/snaptrade-user'
import { decryptSecret } from '@/lib/crypto/secret-box'
import { getProductionPauseState } from '@/lib/tradier'
import {
  canOpenForCustomer,
  condorCloseLegs,
  condorOpenLegs,
  sizeContracts,
  spreadCloseLegs,
  spreadOpenLegs,
  type MlegLegSpec,
} from './contracts'

export interface MasterOpen {
  botName: string
  positionId: string
  ticker: string
  expiration: string // YYYY-MM-DD
  putShort: number
  putLong: number
  callShort: number // 0 → 2-leg put credit spread (FLAME)
  callLong: number
  spreadWidth: number
  credit: number
}

interface EligibleRow {
  activation_id: string
  activation_status: string
  config_id: string
  user_id: string
  config_json: Record<string, unknown> | null
  broker_account_id: string
  external_account_ref_ciphertext: string | null
  buying_power_cents: string | number | null
  connection_status: string | null
  provider: string | null
  subscription_status: string | null
}

const CUSTOMER_AGENTS = new Set(['spark', 'flame'])
const MAX_CLOSE_ATTEMPTS = 3

// Defined in ./armed so read paths (the Live summary, the customer disclosure)
// can ask without importing SnapTrade and the customers DB. Imported AND
// re-exported: this module gates on it itself (canOpenForCustomer below), and a
// bare `export ... from` would re-export it without creating a local binding.
import { isExecutorArmed } from './armed'
export { isExecutorArmed }

/** Ops push for fills and (urgently) failures. Best-effort; the DB row is the record. */
async function notifyOps(title: string, body: string, urgent = false): Promise<void> {
  const topic = process.env.ALERT_NTFY_TOPIC
  if (!topic) return
  try {
    await fetch(`https://ntfy.sh/${encodeURIComponent(topic)}`, {
      method: 'POST',
      headers: {
        Title: title,
        Tags: urgent ? 'rotating_light' : 'robot',
        ...(urgent ? { Priority: 'urgent' } : {}),
      },
      body,
    })
  } catch { /* best-effort */ }
}

function toSdkLegs(legs: MlegLegSpec[]) {
  return legs.map((l) => ({
    instrument: { symbol: l.symbol, instrument_type: 'OPTION' as const },
    action: l.action,
    units: l.units,
  }))
}

/** One newest live activation per customer for this agent, with everything the gates need. */
async function eligibleCustomers(agent: string): Promise<EligibleRow[]> {
  return customerQuery<EligibleRow>(
    `SELECT DISTINCT ON (ac.user_id)
            a.id AS activation_id, a.status AS activation_status,
            ac.id AS config_id, ac.user_id, ac.config_json,
            ba.id AS broker_account_id, ba.external_account_ref_ciphertext, ba.buying_power_cents,
            bc.status AS connection_status, bc.provider,
            s.status AS subscription_status
       FROM activations a
       JOIN agent_configs ac ON ac.id = a.config_id
       JOIN broker_accounts ba ON ba.id = ac.broker_account_id
       JOIN brokerage_connections bc ON bc.id = ba.connection_id
       LEFT JOIN customer_bot_subscriptions s ON s.user_id = ac.user_id AND s.bot = ac.agent_code
      WHERE ac.agent_code = $1
        AND a.status IN ('active', 'paused')
      ORDER BY ac.user_id, a.activated_at DESC NULLS LAST, a.created_at DESC`,
    [agent],
  )
}

async function markSkipped(rowId: string, reason: string): Promise<void> {
  await customerExecute(
    `UPDATE customer_positions SET status = 'skipped', skip_reason = $2, updated_at = now() WHERE id = $1`,
    [rowId, reason],
  )
}

async function mirrorOneOpen(c: EligibleRow, m: MasterOpen, agent: string, killSwitchEngaged: boolean): Promise<void> {
  // Claim FIRST: the (source_position_id, user_id) unique index is the restart-proof
  // double-place guard. rowCount 0 = another process/cycle already handled this pair.
  const claimed = await customerExecute(
    `INSERT INTO customer_positions
       (user_id, activation_id, config_id, agent_code, source_position_id, broker_account_id,
        ticker, expiration, put_short, put_long, call_short, call_long, status)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'claimed')
     ON CONFLICT (source_position_id, user_id) DO NOTHING`,
    [c.user_id, c.activation_id, c.config_id, agent, m.positionId, c.broker_account_id,
     m.ticker, m.expiration, m.putShort, m.putLong, m.callShort, m.callLong],
  )
  if (claimed === 0) return

  const rows = await customerQuery<{ id: string }>(
    `SELECT id FROM customer_positions WHERE source_position_id = $1 AND user_id = $2 LIMIT 1`,
    [m.positionId, c.user_id],
  )
  const rowId = rows[0]?.id
  if (!rowId) return

  const gate = canOpenForCustomer({
    executorArmed: isExecutorArmed(),
    killSwitchEngaged,
    subscriptionStatus: c.subscription_status,
    customerPaused: c.activation_status === 'paused',
    activationActive: c.activation_status === 'active' || c.activation_status === 'paused',
    connectionActive: c.connection_status === 'active',
  })
  if (!gate.allow) { await markSkipped(rowId, gate.reason); return }
  if (c.provider !== 'snaptrade') { await markSkipped(rowId, 'unsupported_provider'); return }
  if (!c.external_account_ref_ciphertext) { await markSkipped(rowId, 'no_account_ref'); return }

  const creds = await loadSnapTradeCreds(c.user_id)
  if (!creds) { await markSkipped(rowId, 'no_broker_credentials'); return }
  const accountId = decryptSecret(c.external_account_ref_ciphertext)
  const snaptrade = getSnapTrade()

  // Live buying power for sizing; stored value (from connect/preview) as fallback.
  // sizeContracts fails to zero if both are unknown — never guess a position size.
  let bpCents: number | null = c.buying_power_cents != null ? Math.floor(Number(c.buying_power_cents)) : null
  let bpSource = 'stored'
  try {
    const bal = await snaptrade.accountInformation.getUserAccountBalance({
      userId: creds.snaptradeUserId, userSecret: creds.userSecret, accountId,
    })
    const balRows = Array.isArray(bal.data) ? (bal.data as Array<{ buying_power?: number | null; cash?: number | null }>) : []
    const live = balRows[0]?.buying_power ?? balRows[0]?.cash ?? null
    if (live != null && Number.isFinite(Number(live))) {
      bpCents = Math.floor(Number(live) * 100)
      bpSource = 'live'
    }
  } catch { /* stored fallback */ }

  const cfg = (c.config_json ?? {}) as { max_deployment_pct?: number }
  const pct = Number(cfg.max_deployment_pct)
  if (!Number.isFinite(pct) || pct <= 0 || pct > 100) { await markSkipped(rowId, 'bad_config'); return }
  const maxDeploymentCents = Math.floor(((bpCents ?? 0) * pct) / 100)

  const sizing = sizeContracts({
    buyingPowerCents: bpCents,
    maxDeploymentCents,
    spreadWidth: m.spreadWidth,
    creditPerSpread: m.credit,
  })
  if (sizing.contracts < 1) { await markSkipped(rowId, sizing.reason ?? 'below_one_contract'); return }

  const legs = m.callShort > 0
    ? condorOpenLegs({ ticker: m.ticker, expiration: m.expiration, putShort: m.putShort, putLong: m.putLong, callShort: m.callShort, callLong: m.callLong }, sizing.contracts)
    : spreadOpenLegs({ ticker: m.ticker, expiration: m.expiration, short: m.putShort, long: m.putLong, right: 'P' }, sizing.contracts)

  // MARKET + Day mirrors the master's own production placement (multileg market orders).
  const placed = await snaptrade.trading.placeMlegOrder({
    userId: creds.snaptradeUserId,
    userSecret: creds.userSecret,
    accountId,
    order_type: 'MARKET',
    time_in_force: 'Day',
    legs: toSdkLegs(legs),
  })
  const orderId = (placed.data as { brokerage_order_id?: string })?.brokerage_order_id ?? null

  await customerExecute(
    `UPDATE customer_positions
        SET status = 'open', contracts = $2, collateral_cents = $3, open_order_id = $4,
            opened_at = now(), updated_at = now(), detail_json = $5
      WHERE id = $1`,
    [rowId, sizing.contracts, sizing.collateralPerSpreadCents * sizing.contracts, orderId,
     JSON.stringify({ bp_cents: bpCents, bp_source: bpSource, max_deployment_pct: pct, master_credit: m.credit })],
  )
  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CUSTOMER_ORDER_PLACED', $2)`,
    [c.user_id, JSON.stringify({ source_position_id: m.positionId, agent, contracts: sizing.contracts, order_id: orderId })],
  ).catch(() => {})
  void notifyOps(
    `IronForge: ${agent.toUpperCase()} mirrored`,
    `${sizing.contracts}x ${m.ticker} for customer ${c.user_id.slice(0, 8)} (order ${orderId ?? 'n/a'}, BP ${bpSource})`,
  )
}

/**
 * Mirror a just-opened master position to every eligible customer. Fire-and-forget
 * from the scanner (`void mirrorOpenToCustomers(...)`); never throws.
 */
export async function mirrorOpenToCustomers(m: MasterOpen): Promise<void> {
  try {
    if (!isExecutorArmed()) return
    if (!isCustomersDbConfigured() || !isSnapTradeConfigured()) return
    const agent = m.botName.toLowerCase()
    if (!CUSTOMER_AGENTS.has(agent)) return

    // Fleet kill switch: the same production pause that halts the master's real-money
    // accounts halts customer mirroring. Unknown reads as ENGAGED (fail closed).
    let killSwitchEngaged = true
    try { killSwitchEngaged = (await getProductionPauseState(agent)).paused } catch { killSwitchEngaged = true }

    const customers = await eligibleCustomers(agent)
    for (const c of customers) {
      try {
        await mirrorOneOpen(c, m, agent, killSwitchEngaged)
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        console.error(`[customer-executor] open mirror failed for user ${c.user_id}: ${msg}`)
        await customerExecute(
          `UPDATE customer_positions SET status = 'error', error = $3, updated_at = now()
            WHERE source_position_id = $1 AND user_id = $2 AND status = 'claimed'`,
          [m.positionId, c.user_id, msg.slice(0, 500)],
        ).catch(() => {})
        void notifyOps('IronForge: customer OPEN failed', `${agent.toUpperCase()} ${m.positionId} → user ${c.user_id.slice(0, 8)}: ${msg.slice(0, 180)}`, true)
      }
    }
  } catch (e) {
    console.error('[customer-executor] mirrorOpenToCustomers sweep failed:', e instanceof Error ? e.message : e)
  }
}

interface OpenCustomerPosition {
  id: string
  user_id: string
  agent_code: string
  ticker: string
  expiration: string
  put_short: string | number
  put_long: string | number
  call_short: string | number
  call_long: string | number
  contracts: number
  close_attempts: number
}

async function closeOne(p: OpenCustomerPosition, reason: string): Promise<void> {
  // Claim the close transition so a double-fired hook can't double-close. Stale
  // close_pending rows (crash mid-close) are re-claimable: the claim refreshes
  // updated_at, so the 15-min staleness window rate-limits re-drives.
  const claimed = await customerExecute(
    `UPDATE customer_positions SET status = 'close_pending', close_attempts = close_attempts + 1, updated_at = now()
      WHERE id = $1
        AND (status IN ('open', 'close_failed')
             OR (status = 'close_pending' AND updated_at < now() - interval '15 minutes'))`,
    [p.id],
  )
  if (claimed === 0) return

  const creds = await loadSnapTradeCreds(p.user_id)
  const refRows = await customerQuery<{ external_account_ref_ciphertext: string | null }>(
    `SELECT ba.external_account_ref_ciphertext
       FROM customer_positions cp JOIN broker_accounts ba ON ba.id = cp.broker_account_id
      WHERE cp.id = $1`,
    [p.id],
  )
  const enc = refRows[0]?.external_account_ref_ciphertext
  if (!creds || !enc) {
    await customerExecute(
      `UPDATE customer_positions SET status = 'close_failed', error = 'missing broker credentials at close', updated_at = now() WHERE id = $1`,
      [p.id],
    )
    void notifyOps('IronForge: customer CLOSE blocked', `No broker credentials for user ${p.user_id.slice(0, 8)} — position ${p.id} needs a MANUAL close`, true)
    return
  }
  const accountId = decryptSecret(enc)

  const exp = typeof p.expiration === 'string' ? p.expiration.slice(0, 10) : String(p.expiration).slice(0, 10)
  const callShort = Number(p.call_short)
  const legs = callShort > 0
    ? condorCloseLegs({ ticker: p.ticker, expiration: exp, putShort: Number(p.put_short), putLong: Number(p.put_long), callShort, callLong: Number(p.call_long) }, p.contracts)
    : spreadCloseLegs({ ticker: p.ticker, expiration: exp, short: Number(p.put_short), long: Number(p.put_long), right: 'P' }, p.contracts)

  const snaptrade = getSnapTrade()
  let lastErr = ''
  for (let attempt = 1; attempt <= MAX_CLOSE_ATTEMPTS; attempt++) {
    try {
      const placed = await snaptrade.trading.placeMlegOrder({
        userId: creds.snaptradeUserId,
        userSecret: creds.userSecret,
        accountId,
        order_type: 'MARKET',
        time_in_force: 'Day',
        legs: toSdkLegs(legs),
      })
      const orderId = (placed.data as { brokerage_order_id?: string })?.brokerage_order_id ?? null
      await customerExecute(
        `UPDATE customer_positions
            SET status = 'closed', close_order_id = $2, close_reason = $3, closed_at = now(), updated_at = now(), error = NULL
          WHERE id = $1`,
        [p.id, orderId, reason.slice(0, 120)],
      )
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CUSTOMER_ORDER_CLOSED', $2)`,
        [p.user_id, JSON.stringify({ position: p.id, reason, order_id: orderId })],
      ).catch(() => {})
      return
    } catch (e) {
      lastErr = e instanceof Error ? e.message : String(e)
      if (attempt < MAX_CLOSE_ATTEMPTS) await new Promise((r) => setTimeout(r, 2000 * attempt))
    }
  }
  // An unclosed customer position is REAL RISK sitting in a real account: mark it,
  // scream, and let the 15-min retry sweep keep trying during market hours.
  await customerExecute(
    `UPDATE customer_positions SET status = 'close_failed', error = $2, updated_at = now() WHERE id = $1`,
    [p.id, lastErr.slice(0, 500)],
  )
  void notifyOps(
    'IronForge: customer CLOSE FAILED',
    `${p.agent_code.toUpperCase()} position ${p.id} (user ${p.user_id.slice(0, 8)}) failed ${MAX_CLOSE_ATTEMPTS} close attempts: ${lastErr.slice(0, 180)}. Retry sweep is on; may need a manual close.`,
    true,
  )
}

/**
 * Close every customer mirror of a master position. Fire-and-forget from
 * closePosition; never throws. Deliberately NOT gated on the arming flag —
 * if the flag is flipped off with positions open, they must still close.
 */
export async function mirrorCloseToCustomers(botName: string, sourcePositionId: string, reason: string): Promise<void> {
  try {
    if (!isCustomersDbConfigured() || !isSnapTradeConfigured()) return
    if (!CUSTOMER_AGENTS.has(botName.toLowerCase())) return
    const open = await customerQuery<OpenCustomerPosition>(
      `SELECT id, user_id, agent_code, ticker, expiration::text AS expiration,
              put_short, put_long, call_short, call_long, contracts, close_attempts
         FROM customer_positions
        WHERE source_position_id = $1 AND status = 'open'`,
      [sourcePositionId],
    )
    for (const p of open) {
      try {
        await closeOne(p, reason)
      } catch (e) {
        console.error(`[customer-executor] close mirror failed for ${p.id}:`, e instanceof Error ? e.message : e)
      }
    }
  } catch (e) {
    console.error('[customer-executor] mirrorCloseToCustomers sweep failed:', e instanceof Error ? e.message : e)
  }
}

let _closeRetryRunning = false

/**
 * Safety net for close_failed rows: re-drive them during market hours from the
 * scanner's 15-min satellite interval. The close hook fires once per master close;
 * without this sweep a transient broker outage would strand customer risk until a
 * human noticed the ntfy alert.
 */
export function retryFailedCustomerCloses(): void {
  if (_closeRetryRunning) return
  if (!isCustomersDbConfigured() || !isSnapTradeConfigured()) return

  // Rough RTH gate (CT): market orders outside hours just reject and burn attempts.
  const ct = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Chicago' }))
  const hhmm = ct.getHours() * 100 + ct.getMinutes()
  const weekday = ct.getDay() >= 1 && ct.getDay() <= 5
  if (!weekday || hhmm < 835 || hhmm > 1455) return

  _closeRetryRunning = true
  ;(async () => {
    // close_failed = broker rejected N attempts. Stale close_pending = process died
    // mid-close; re-driving is safe because close-side legs on a flat position are
    // rejected by the broker rather than opening new risk.
    const stuck = await customerQuery<OpenCustomerPosition & { close_reason: string | null }>(
      `SELECT id, user_id, agent_code, ticker, expiration::text AS expiration,
              put_short, put_long, call_short, call_long, contracts, close_attempts, close_reason
         FROM customer_positions
        WHERE status = 'close_failed'
           OR (status = 'close_pending' AND updated_at < now() - interval '15 minutes')`,
    )
    for (const p of stuck) {
      try {
        await closeOne(p, p.close_reason ?? 'retry_sweep')
      } catch (e) {
        console.error(`[customer-executor] close retry failed for ${p.id}:`, e instanceof Error ? e.message : e)
      }
    }
  })()
    .catch((e: unknown) => {
      console.warn('[customer-executor] retryFailedCustomerCloses error:', e instanceof Error ? e.message : e)
    })
    .finally(() => { _closeRetryRunning = false })
}
