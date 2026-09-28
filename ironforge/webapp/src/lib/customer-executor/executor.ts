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
import { normalizeInstitutionSlug } from '@/lib/enrollment/eligibility'
import { flintMaxLoss } from '@/lib/flint'
import {
  canOpenForCustomer,
  condorCloseLegs,
  condorOpenLegs,
  evaluateCalmUpsize,
  evaluateDepositFloorCap,
  evaluateFastStartUpsize,
  evaluateFlintCushion,
  sizeContracts,
  spreadCloseLegs,
  spreadOpenLegs,
  type MlegLegSpec,
} from './contracts'
import { checkBotTradedAccount, type BotAccountGuardVerdict } from './bot-account-guard'
import { getKnownBotTradedTradierAccountNumbers } from './bot-account-registry'

/** 0.70 — the frozen "calm" VIX-decay-ratio threshold shared by B1 and the house-money calm-upsize. */
const CALM_VIX_CEILING = 0.70
/** $4,000 in cents — the frozen minimum deposit for the house-money calm-upsize (Round 4). */
const CALM_UPSIZE_MIN_DEPOSIT_CENTS = 400_000

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
  /**
   * Explicit leg-shape override. Optional and back-compat: every pre-existing call site
   * omits it, so the inference below (`callShort > 0` → condor, else put spread) stays
   * byte-for-byte unchanged for FLAME/SPARK's main leg. FLINT's mirror sets this to
   * 'call_spread' explicitly — inferring it from strikes alone would be ambiguous/wrong,
   * since a call spread also has callShort > 0 but putShort/putLong are 0 (not a condor).
   */
  legKind?: 'condor' | 'put_spread' | 'call_spread'
  /**
   * Today's VIX-decay ratio (same signal FLINT's day-eligibility reads), for
   * CUSTOMER_FAST_START (B1) and CUSTOMER_CALM_UPSIZE. Optional/null-safe: every
   * pre-existing call site can omit it (both features simply never fire, same as
   * their flags being off) — see resolveLegKind's doc for the same back-compat pattern.
   */
  vixRatio?: number | null
}

export function resolveLegKind(m: Pick<MasterOpen, 'legKind' | 'callShort'>): 'condor' | 'put_spread' | 'call_spread' {
  if (m.legKind) return m.legKind
  return m.callShort > 0 ? 'condor' : 'put_spread'
}

interface EligibleRow {
  activation_id: string
  activation_status: string
  config_id: string
  user_id: string
  config_json: Record<string, unknown> | null
  broker_account_id: string
  external_account_ref_ciphertext: string | null
  display_mask: string | null
  brokerage_slug: string | null
  buying_power_cents: string | number | null
  connection_status: string | null
  provider: string | null
  subscription_status: string | null
}

const CUSTOMER_AGENTS = new Set(['spark', 'flame'])
const MAX_CLOSE_ATTEMPTS = 3
/** $50/contract, matching customer_protection_sim.py's MARGIN constant — see contracts.ts evaluateFlintCushion. */
const FLINT_CUSHION_MARGIN_CENTS = 5000

export function isExecutorArmed(): boolean {
  return process.env.CUSTOMER_EXECUTOR_ENABLED === 'true'
}

/**
 * FLINT customer mirroring master switch. Default OFF (unset/anything but the exact
 * string 'on' reads as off — fails closed, same convention as FLINT_MODE in flint.ts).
 * This gates ONLY the FLINT sleeve; it is layered on TOP of isExecutorArmed() below,
 * never a replacement for it — both must be true for a FLINT customer order to place.
 */
export function isCustomerFlintEnabled(): boolean {
  return String(process.env.CUSTOMER_FLINT ?? '').trim().toLowerCase() === 'on'
}

/**
 * CUSTOMER_DEPOSIT_FLOOR master switch. Default OFF, fails closed on any value other
 * than the exact string 'on' — same convention as isCustomerFlintEnabled(). Independent
 * of both isExecutorArmed() and isCustomerFlintEnabled(); it caps the MAIN leg's sizing
 * (mirrorOneOpen) and, when on, additionally tightens FLINT's own cushion check.
 */
export function isCustomerDepositFloorEnabled(): boolean {
  return String(process.env.CUSTOMER_DEPOSIT_FLOOR ?? '').trim().toLowerCase() === 'on'
}

/**
 * CUSTOMER_FAST_START (B1) master switch. Default OFF, fails closed on any value
 * other than 'on'. Requires CUSTOMER_DEPOSIT_FLOOR to ALSO be on — B1 is defined in
 * terms of "before the floor triggers," which is meaningless without the floor's own
 * triggered-state tracking running (see mirrorOneOpen).
 */
export function isCustomerFastStartEnabled(): boolean {
  return String(process.env.CUSTOMER_FAST_START ?? '').trim().toLowerCase() === 'on'
}

/**
 * CUSTOMER_CALM_UPSIZE master switch. Default OFF, fails closed on any value other
 * than 'on'. This is the house-money, POST-trigger calm add-on (Round 4); it does NOT
 * require CUSTOMER_DEPOSIT_FLOOR to be on for its OWN gate math (protect_level is
 * always `deposit`), but in mirrorOneOpen it only ever gets a chance to fire when the
 * floor is on and triggered — see the doc there.
 */
export function isCustomerCalmUpsizeEnabled(): boolean {
  return String(process.env.CUSTOMER_CALM_UPSIZE ?? '').trim().toLowerCase() === 'on'
}

const DEPOSIT_FLOOR_N = 3 // frozen ROUND 3 winner (K=0, N=3, variant S) — see contracts.ts evaluateDepositFloorCap
/** $50/contract, matching customer_protection_sim.py's MARGIN constant — shared with FLINT's own margin. */
const DEPOSIT_FLOOR_MARGIN_CENTS = 5000

interface DepositFloorStateRow {
  deposit_cents: string | number
  triggered: boolean
}

/**
 * Reads/creates the sticky per-(customer, bot) floor state, applies evaluateDepositFloorCap,
 * and persists any trigger transition + a fresh equity snapshot. FAILS OPEN on any read/write
 * problem (see contracts.ts's doc comment on evaluateDepositFloorCap for why): the caller gets
 * `dataOk: false` and MUST use `desiredContracts` unmodified, logging that the floor could not
 * be evaluated rather than silently skipping the trade.
 */
async function applyDepositFloor(args: {
  userId: string
  agent: string
  depositCents: number | null // the SAME "deposit" proxy FLINT uses (broker_accounts.buying_power_cents at connect)
  equityCents: number | null
  pct: number
  maxLossCentsPerContract: number
  desiredContracts: number
}): Promise<ReturnType<typeof evaluateDepositFloorCap>> {
  const fallback = { contracts: Math.max(0, args.desiredContracts), triggeredNow: false, capped: false, dataOk: false, triggeredForSizing: false }
  if (args.depositCents == null) {
    console.warn(`[customer-executor] deposit floor: no deposit baseline for user ${args.userId}/${args.agent} — using today's normal sizing (logged, per spec)`)
    return fallback
  }
  try {
    let state = (await customerQuery<DepositFloorStateRow>(
      `SELECT deposit_cents, triggered FROM customer_deposit_floor_state WHERE user_id = $1 AND agent_code = $2`,
      [args.userId, args.agent],
    ))[0]
    if (!state) {
      await customerExecute(
        `INSERT INTO customer_deposit_floor_state (user_id, agent_code, deposit_cents, triggered)
         VALUES ($1, $2, $3, FALSE)
         ON CONFLICT (user_id, agent_code) DO NOTHING`,
        [args.userId, args.agent, Math.round(args.depositCents)],
      )
      state = { deposit_cents: Math.round(args.depositCents), triggered: false }
    }
    const depositCents = Math.floor(Number(state.deposit_cents))
    const result = evaluateDepositFloorCap({
      equityCents: args.equityCents,
      depositCents,
      maxLossCentsPerContract: args.maxLossCentsPerContract,
      marginCents: DEPOSIT_FLOOR_MARGIN_CENTS,
      pct: args.pct,
      desiredContracts: args.desiredContracts,
      triggered: state.triggered,
      triggerN: DEPOSIT_FLOOR_N,
    })
    if (!result.dataOk) {
      console.warn(`[customer-executor] deposit floor: bad inputs for user ${args.userId}/${args.agent} — using today's normal sizing (logged, per spec)`)
      return result
    }
    await customerExecute(
      `UPDATE customer_deposit_floor_state
          SET triggered = triggered OR $3, trigger_date = COALESCE(trigger_date, CASE WHEN $3 THEN CURRENT_DATE END),
              last_equity_cents = $4, last_equity_at = now(), updated_at = now()
        WHERE user_id = $1 AND agent_code = $2`,
      [args.userId, args.agent, result.triggeredNow, args.equityCents],
    )
    return result
  } catch (e) {
    console.error(`[customer-executor] deposit floor evaluation failed for user ${args.userId}/${args.agent} (fails OPEN, today's normal sizing used):`, e instanceof Error ? e.message : e)
    return fallback
  }
}

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
            ba.display_mask, bc.brokerage_slug,
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

/** Decrypt for the bot-account guard only. A malformed/foreign ciphertext must read
 *  as "unknown", never throw — the guard's fail-closed behavior handles unknown. */
function safeDecryptAccountRef(ciphertext: string | null | undefined): string | null {
  if (!ciphertext) return null
  try {
    return decryptSecret(ciphertext)
  } catch {
    return null
  }
}

/** One human-readable line for logs/alerts. Never includes the full account number. */
function describeBotAccountBlock(v: BotAccountGuardVerdict): string {
  if (!v.blocked) return 'not blocked'
  if (v.reason === 'unverifiable') return 'unverifiable account — skipped'
  return `bot-traded account (${v.reason}, ****${v.matchedLast4}) — skipped`
}

/**
 * 6YB71371 double-trade guard: is this customer's broker account one the bots
 * already trade directly (SPARK/FLAME production, or another env-listed account)?
 * Checked before EVERY open and close mirror — see bot-account-guard.ts. This
 * includes FLINT's own open (mirrorOneFlintOpen) and every FLINT close, not just
 * the main leg — a bot-traded account must never receive ANY customer-mirrored
 * order, regardless of which sleeve it came from.
 */
function checkCustomerAgainstBotAccounts(row: {
  external_account_ref_ciphertext: string | null
  display_mask: string | null
  brokerage_slug: string | null
}): BotAccountGuardVerdict {
  return checkBotTradedAccount({
    decryptedAccountRef: safeDecryptAccountRef(row.external_account_ref_ciphertext),
    displayMask: row.display_mask,
    brokerSlug: normalizeInstitutionSlug(row.brokerage_slug),
    knownBotAccountNumbers: getKnownBotTradedTradierAccountNumbers(),
  })
}

async function mirrorOneOpen(
  c: EligibleRow, m: MasterOpen, agent: string, killSwitchEngaged: boolean, strategy: 'main' | 'flint' = 'main',
): Promise<void> {
  const legKind = resolveLegKind(m)
  // Claim FIRST: the (source_position_id, user_id) unique index is the restart-proof
  // double-place guard. rowCount 0 = another process/cycle already handled this pair.
  const claimed = await customerExecute(
    `INSERT INTO customer_positions
       (user_id, activation_id, config_id, agent_code, source_position_id, broker_account_id,
        ticker, expiration, put_short, put_long, call_short, call_long, status, leg_kind, strategy)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'claimed', $13, $14)
     ON CONFLICT (source_position_id, user_id) DO NOTHING`,
    [c.user_id, c.activation_id, c.config_id, agent, m.positionId, c.broker_account_id,
     m.ticker, m.expiration, m.putShort, m.putLong, m.callShort, m.callLong, legKind, strategy],
  )
  if (claimed === 0) return

  const rows = await customerQuery<{ id: string }>(
    `SELECT id FROM customer_positions WHERE source_position_id = $1 AND user_id = $2 LIMIT 1`,
    [m.positionId, c.user_id],
  )
  const rowId = rows[0]?.id
  if (!rowId) return

  // Hard invariant, checked FIRST and independent of every other gate below: never
  // mirror an open into an account the bots already trade directly (6YB71371
  // double-trade guard). FAILS CLOSED — an account we cannot verify is treated the
  // same as a confirmed match.
  const botGuard = checkCustomerAgainstBotAccounts(c)
  if (botGuard.blocked) {
    const detail = describeBotAccountBlock(botGuard)
    await markSkipped(rowId, `bot_account_guard:${botGuard.reason}`)
    console.error(`[customer-executor] OPEN BLOCKED for user ${c.user_id.slice(0, 8)}: ${detail}`)
    void notifyOps(
      'IronForge: customer OPEN blocked (bot account guard)',
      `${agent.toUpperCase()} ${m.positionId} → user ${c.user_id.slice(0, 8)}: ${detail}`,
      true,
    )
    return
  }

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

  // CUSTOMER_DEPOSIT_FLOOR (2026-09-28): caps sizing.contracts DOWN, never up, once a
  // customer's own cushion has crossed the trigger — see contracts.ts evaluateDepositFloorCap.
  // Off (default) or any evaluation failure: contracts stays exactly sizing.contracts,
  // byte-identical to today. `bpCents` doubles as "equity" here — the same live read
  // sizing already used, no extra broker call.
  let finalContracts = sizing.contracts
  let depositFloorNote: Record<string, unknown> | null = null
  if (isCustomerDepositFloorEnabled()) {
    const depositCents = c.buying_power_cents != null ? Math.floor(Number(c.buying_power_cents)) : null
    const floorResult = await applyDepositFloor({
      userId: c.user_id, agent, depositCents,
      equityCents: bpCents, pct, maxLossCentsPerContract: sizing.collateralPerSpreadCents, desiredContracts: sizing.contracts,
    })
    finalContracts = floorResult.contracts
    depositFloorNote = {
      data_ok: floorResult.dataOk, triggered_now: floorResult.triggeredNow, capped: floorResult.capped,
      triggered_for_sizing: floorResult.triggeredForSizing, desired_contracts: sizing.contracts, final_contracts: finalContracts,
    }
    if (finalContracts < 1) {
      await markSkipped(rowId, floorResult.dataOk ? 'deposit_floor_capped_to_zero' : 'below_one_contract')
      return
    }

    // CUSTOMER_FAST_START (B1, pre-trigger) and CUSTOMER_CALM_UPSIZE (house-money,
    // post-trigger) are mutually exclusive per day — customer_protection_final_package.py's
    // if/else — decided by floorResult.triggeredForSizing. Only meaningful when
    // dataOk (an unreadable floor evaluation has no well-defined pre/post regime).
    if (floorResult.dataOk && !floorResult.triggeredForSizing && isCustomerFastStartEnabled()) {
      const b1 = evaluateFastStartUpsize({
        triggeredForSizing: floorResult.triggeredForSizing, baseContracts: finalContracts,
        vixRatio: m.vixRatio ?? null, vixCeiling: CALM_VIX_CEILING,
      })
      if (b1.extraContract) finalContracts += 1
      depositFloorNote.fast_start = { applied: b1.extraContract, reason: b1.reason }
    } else if (floorResult.dataOk && floorResult.triggeredForSizing && isCustomerCalmUpsizeEnabled()) {
      const calm = evaluateCalmUpsize({
        equityCents: bpCents, depositCents, baseContracts: finalContracts,
        maxLossCentsPerContract: sizing.collateralPerSpreadCents, marginCents: FLINT_CUSHION_MARGIN_CENTS,
        vixRatio: m.vixRatio ?? null, vixCeiling: CALM_VIX_CEILING, minDepositCentsForUpsize: CALM_UPSIZE_MIN_DEPOSIT_CENTS,
      })
      if (calm.extraContract) finalContracts += 1
      depositFloorNote.calm_upsize = { applied: calm.extraContract, reason: calm.reason }
    }
  }

  const legs = legKind === 'call_spread'
    ? spreadOpenLegs({ ticker: m.ticker, expiration: m.expiration, short: m.callShort, long: m.callLong, right: 'C' }, finalContracts)
    : legKind === 'condor'
      ? condorOpenLegs({ ticker: m.ticker, expiration: m.expiration, putShort: m.putShort, putLong: m.putLong, callShort: m.callShort, callLong: m.callLong }, finalContracts)
      : spreadOpenLegs({ ticker: m.ticker, expiration: m.expiration, short: m.putShort, long: m.putLong, right: 'P' }, finalContracts)

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
    [rowId, finalContracts, sizing.collateralPerSpreadCents * finalContracts, orderId,
     JSON.stringify({ bp_cents: bpCents, bp_source: bpSource, max_deployment_pct: pct, master_credit: m.credit, deposit_floor: depositFloorNote })],
  )
  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CUSTOMER_ORDER_PLACED', $2)`,
    [c.user_id, JSON.stringify({ source_position_id: m.positionId, agent, contracts: finalContracts, order_id: orderId })],
  ).catch(() => {})
  void notifyOps(
    `IronForge: ${agent.toUpperCase()} mirrored`,
    `${finalContracts}x ${m.ticker} for customer ${c.user_id.slice(0, 8)} (order ${orderId ?? 'n/a'}, BP ${bpSource})`,
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

/**
 * ─────────────────────────────────────────────────────────────────────────
 * FLINT customer mirroring (CUSTOMER_FLINT) — profits-only, 1 contract.
 *
 * Ships DISARMED behind isCustomerFlintEnabled() (CUSTOMER_FLINT === 'on'),
 * layered on top of the base executor arm (isExecutorArmed()) — both must be
 * true. Off = zero DB/broker calls from this block, byte-identical to today.
 *
 * Eligibility ports customer_protection_sim.py's P3 arm (see contracts.ts
 * evaluateFlintCushion for the full citation): a customer's FLINT mirror
 * fires ONLY when equity - protectLevel already covers FLINT's own max loss
 * (+ a $50/contract margin, Leron's explicit instruction — the sim's exact
 * P3 formula has no margin term; see the parity test for the margin-free
 * comparison against sim fixtures). protectLevel is the customer's deposit —
 * no profit-floor/ratchet exists for customers yet (that's the sim's
 * unshipped P1/P2 arm), so protectLevel === depositCents unconditionally.
 *
 * "Deposit" and "equity" data-source note (there is no funded-account ledger
 * for customers — they link an EXISTING brokerage account via SnapTrade):
 *   - depositCents = broker_accounts.buying_power_cents, captured ONCE at
 *     connect/sync time (before any bot activity) — see customers-db.ts's
 *     comment on that column ("Captured at sync"). It is never re-written
 *     after connect, so it is a stable baseline, exactly like the sim's
 *     fixed `deposit`.
 *   - equityCents = a FRESH live SnapTrade balance read at mirror time (the
 *     same buying-power-or-cash call the main leg already uses for sizing
 *     in mirrorOneOpen above) — never the stale connect-time snapshot.
 * This is a documented approximation (buying power, not true net-liq — no
 * net-liq field is tracked anywhere in this codebase today); flagged as a
 * sim-vs-live difference, not silently assumed.
 * ─────────────────────────────────────────────────────────────────────────
 */
export interface FlintMasterOpen {
  botName: string // 'flame' | 'spark'
  positionId: string
  ticker: string
  expiration: string // YYYY-MM-DD
  callShort: number
  callLong: number
  spreadWidth: number
  credit: number
  /** YYYY-MM-DD trading day this decision belongs to (one row per customer per day). */
  tradeDate: string
}

interface FlintDecisionRow {
  tradeDate: string
  userId: string
  agentCode: string
  sourcePositionId: string
  eligible: boolean
  reason: string
  equityCents: number | null
  depositCents: number | null
  cushionCents: number | null
  maxLossCents: number
  marginCents: number
  contracts: number
}

/** Best-effort audit row. Never throws into the trading path — logging failures are silent. */
async function logFlintDecision(r: FlintDecisionRow): Promise<void> {
  try {
    await customerExecute(
      `INSERT INTO flint_customer_decisions
         (trade_date, user_id, agent_code, source_position_id, eligible, reason,
          equity_cents, deposit_cents, cushion_cents, flint_max_loss_cents, margin_cents, contracts)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
       ON CONFLICT (trade_date, user_id, agent_code) DO UPDATE SET
         source_position_id = EXCLUDED.source_position_id, eligible = EXCLUDED.eligible,
         reason = EXCLUDED.reason, equity_cents = EXCLUDED.equity_cents, deposit_cents = EXCLUDED.deposit_cents,
         cushion_cents = EXCLUDED.cushion_cents, flint_max_loss_cents = EXCLUDED.flint_max_loss_cents,
         margin_cents = EXCLUDED.margin_cents, contracts = EXCLUDED.contracts, created_at = now()`,
      [r.tradeDate, r.userId, r.agentCode, r.sourcePositionId, r.eligible, r.reason,
       r.equityCents, r.depositCents, r.cushionCents, r.maxLossCents, r.marginCents, r.contracts],
    )
  } catch (e) {
    console.error('[customer-executor] flint decision log failed (non-fatal):', e instanceof Error ? e.message : e)
  }
}

async function mirrorOneFlintOpen(c: EligibleRow, m: FlintMasterOpen, agent: string, killSwitchEngaged: boolean): Promise<void> {
  // 1 contract, worst-case max loss including commission — the SAME formula the house
  // account's own rule R1 uses (lib/flint.ts flintMaxLoss), never re-derived independently.
  const maxLossCents = Math.round(flintMaxLoss(m.callShort, m.callLong, m.credit, 1) * 100)

  const logSkip = (reason: string, equityCents: number | null = null, depositCents: number | null = null, cushionCents: number | null = null) =>
    logFlintDecision({
      tradeDate: m.tradeDate, userId: c.user_id, agentCode: agent, sourcePositionId: m.positionId,
      eligible: false, reason, equityCents, depositCents, cushionCents,
      maxLossCents, marginCents: FLINT_CUSHION_MARGIN_CENTS, contracts: 0,
    })

  // Hard invariant, checked FIRST and independent of every other gate below — same
  // rule, same order, as mirrorOneOpen: never mirror a FLINT open into an account the
  // bots already trade directly (6YB71371 double-trade guard). FAILS CLOSED.
  const botGuard = checkCustomerAgainstBotAccounts(c)
  if (botGuard.blocked) {
    const detail = describeBotAccountBlock(botGuard)
    await logSkip(`bot_account_guard:${botGuard.reason}`)
    console.error(`[customer-executor] FLINT OPEN BLOCKED for user ${c.user_id.slice(0, 8)}: ${detail}`)
    void notifyOps(
      'IronForge: customer FLINT OPEN blocked (bot account guard)',
      `${agent.toUpperCase()} ${m.positionId} → user ${c.user_id.slice(0, 8)}: ${detail}`,
      true,
    )
    return
  }

  const gate = canOpenForCustomer({
    executorArmed: isExecutorArmed(),
    killSwitchEngaged,
    subscriptionStatus: c.subscription_status,
    customerPaused: c.activation_status === 'paused',
    activationActive: c.activation_status === 'active' || c.activation_status === 'paused',
    connectionActive: c.connection_status === 'active',
  })
  if (!gate.allow) { await logSkip(gate.reason); return }
  if (c.provider !== 'snaptrade') { await logSkip('unsupported_provider'); return }
  if (!c.external_account_ref_ciphertext) { await logSkip('no_account_ref'); return }

  const creds = await loadSnapTradeCreds(c.user_id)
  if (!creds) { await logSkip('no_broker_credentials'); return }
  const accountId = decryptSecret(c.external_account_ref_ciphertext)
  const snaptrade = getSnapTrade()

  // Deposit baseline — see the module doc comment above for why this column is the
  // right proxy. Never guessed: a missing baseline skips, same fail-closed convention
  // as everything else in this file.
  const depositCents: number | null = c.buying_power_cents != null ? Math.floor(Number(c.buying_power_cents)) : null

  // Live equity read (fresh, not the stored/stale connect-time snapshot).
  let equityCents: number | null = null
  try {
    const bal = await snaptrade.accountInformation.getUserAccountBalance({
      userId: creds.snaptradeUserId, userSecret: creds.userSecret, accountId,
    })
    const balRows = Array.isArray(bal.data) ? (bal.data as Array<{ buying_power?: number | null; cash?: number | null }>) : []
    const live = balRows[0]?.buying_power ?? balRows[0]?.cash ?? null
    if (live != null && Number.isFinite(Number(live))) equityCents = Math.floor(Number(live) * 100)
  } catch { /* equityCents stays null -> evaluateFlintCushion fails closed below */ }

  const cushion = evaluateFlintCushion({
    equityCents, protectLevelCents: depositCents, maxLossCents, marginCents: FLINT_CUSHION_MARGIN_CENTS,
  })
  if (!cushion.eligible) { await logSkip(cushion.reason ?? 'cushion_insufficient', equityCents, depositCents, cushion.cushionCents); return }

  // CUSTOMER_DEPOSIT_FLOOR combined check ("FLINT is dropped first", Leron's explicit
  // instruction): the standalone cushion check above only looks at FLINT's own max loss
  // in isolation. When the deposit floor is on, the main leg (FLAME/SPARK) may ALSO have
  // already committed real collateral against this SAME account TODAY — two independent
  // legs sharing one real brokerage account's buying power, unlike the sim's single
  // combined equity stream. Combined: equity - deposit must cover BOTH legs' worst case
  // + margin. The main leg's sizing (mirrorOneOpen/applyDepositFloor) is NEVER reduced to
  // make room for FLINT — FLINT alone is dropped if the combined check fails.
  if (isCustomerDepositFloorEnabled()) {
    let mainLegCommittedCents = 0
    try {
      const mainRows = await customerQuery<{ collateral_cents: string | number | null }>(
        `SELECT collateral_cents FROM customer_positions
          WHERE user_id = $1 AND agent_code = $2 AND strategy = 'main' AND status = 'open'
            AND opened_at::date = $3::date
          ORDER BY opened_at DESC LIMIT 1`,
        [c.user_id, agent, m.tradeDate],
      )
      mainLegCommittedCents = mainRows[0]?.collateral_cents != null ? Math.floor(Number(mainRows[0].collateral_cents)) : 0
    } catch (e) {
      // Never guess the main leg's committed risk on a read failure — drop FLINT (it is
      // always safe to skip; the main leg is untouched either way).
      console.error(`[customer-executor] deposit-floor combined check: main-leg read failed for user ${c.user_id} — dropping FLINT:`, e instanceof Error ? e.message : e)
      await logSkip('deposit_floor_combined_unreadable', equityCents, depositCents, cushion.cushionCents)
      return
    }
    const combinedRequired = mainLegCommittedCents + maxLossCents + FLINT_CUSHION_MARGIN_CENTS
    const combinedCushion = (equityCents as number) - (depositCents as number) // both non-null: cushion.eligible already proved it
    if (combinedCushion < combinedRequired) {
      await logSkip('deposit_floor_combined_insufficient', equityCents, depositCents, combinedCushion)
      return
    }
  }

  // Eligible — claim + place exactly 1 contract. Same restart-proof idempotency guard
  // as the main leg (unique index on source_position_id, user_id).
  const claimed = await customerExecute(
    `INSERT INTO customer_positions
       (user_id, activation_id, config_id, agent_code, source_position_id, broker_account_id,
        ticker, expiration, put_short, put_long, call_short, call_long, status, leg_kind, strategy)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,0,0,$9,$10,'claimed','call_spread','flint')
     ON CONFLICT (source_position_id, user_id) DO NOTHING`,
    [c.user_id, c.activation_id, c.config_id, agent, m.positionId, c.broker_account_id,
     m.ticker, m.expiration, m.callShort, m.callLong],
  )
  if (claimed === 0) return // another cycle already placed/claimed this exact (position, customer) pair

  const rows = await customerQuery<{ id: string }>(
    `SELECT id FROM customer_positions WHERE source_position_id = $1 AND user_id = $2 LIMIT 1`,
    [m.positionId, c.user_id],
  )
  const rowId = rows[0]?.id
  if (!rowId) return

  const legs = spreadOpenLegs({ ticker: m.ticker, expiration: m.expiration, short: m.callShort, long: m.callLong, right: 'C' }, 1)
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
        SET status = 'open', contracts = 1, collateral_cents = $2, open_order_id = $3,
            opened_at = now(), updated_at = now(), detail_json = $4
      WHERE id = $1`,
    [rowId, maxLossCents, orderId,
     JSON.stringify({ equity_cents: equityCents, deposit_cents: depositCents, cushion_cents: cushion.cushionCents, master_credit: m.credit, margin_cents: FLINT_CUSHION_MARGIN_CENTS })],
  )
  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CUSTOMER_FLINT_ORDER_PLACED', $2)`,
    [c.user_id, JSON.stringify({ source_position_id: m.positionId, agent, order_id: orderId })],
  ).catch(() => {})
  void notifyOps(
    `IronForge: ${agent.toUpperCase()} FLINT mirrored`,
    `1x ${m.ticker} call spread for customer ${c.user_id.slice(0, 8)} (order ${orderId ?? 'n/a'})`,
  )

  await logFlintDecision({
    tradeDate: m.tradeDate, userId: c.user_id, agentCode: agent, sourcePositionId: m.positionId,
    eligible: true, reason: 'placed', equityCents, depositCents, cushionCents: cushion.cushionCents,
    maxLossCents, marginCents: FLINT_CUSHION_MARGIN_CENTS, contracts: 1,
  })
}

/**
 * Mirror a just-opened FLINT master position to every eligible customer. Fire-and-forget
 * from tryOpenFlint (`void mirrorFlintOpenToCustomers(...)`); never throws.
 */
export async function mirrorFlintOpenToCustomers(m: FlintMasterOpen): Promise<void> {
  try {
    if (!isExecutorArmed() || !isCustomerFlintEnabled()) return
    if (!isCustomersDbConfigured() || !isSnapTradeConfigured()) return
    const agent = m.botName.toLowerCase()
    if (!CUSTOMER_AGENTS.has(agent)) return

    let killSwitchEngaged = true
    try { killSwitchEngaged = (await getProductionPauseState(agent)).paused } catch { killSwitchEngaged = true }

    const customers = await eligibleCustomers(agent)
    for (const c of customers) {
      try {
        await mirrorOneFlintOpen(c, m, agent, killSwitchEngaged)
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        console.error(`[customer-executor] FLINT open mirror failed for user ${c.user_id}: ${msg}`)
        await customerExecute(
          `UPDATE customer_positions SET status = 'error', error = $3, updated_at = now()
            WHERE source_position_id = $1 AND user_id = $2 AND status = 'claimed'`,
          [m.positionId, c.user_id, msg.slice(0, 500)],
        ).catch(() => {})
        await logFlintDecision({
          tradeDate: m.tradeDate, userId: c.user_id, agentCode: agent, sourcePositionId: m.positionId,
          eligible: false, reason: 'error', equityCents: null, depositCents: null, cushionCents: null,
          maxLossCents: Math.round(flintMaxLoss(m.callShort, m.callLong, m.credit, 1) * 100),
          marginCents: FLINT_CUSHION_MARGIN_CENTS, contracts: 0,
        })
        void notifyOps('IronForge: customer FLINT OPEN failed', `${agent.toUpperCase()} ${m.positionId} → user ${c.user_id.slice(0, 8)}: ${msg.slice(0, 180)}`, true)
      }
    }
  } catch (e) {
    console.error('[customer-executor] mirrorFlintOpenToCustomers sweep failed:', e instanceof Error ? e.message : e)
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
  /**
   * 'condor' | 'put_spread' | 'call_spread' | null. Persisted at open time (see
   * mirrorOneOpen/mirrorOneFlintOpen) precisely so CLOSE never has to re-infer the leg
   * shape from strikes alone — inferring from `call_short > 0` is ambiguous for a call
   * spread row (put_short/put_long are legitimately 0/0 there, same as a put-only row
   * with callShort=0 legitimately has no calls; only the explicit tag disambiguates).
   * NULL only for rows opened before this column existed — falls back to the OLD
   * (put-spread/condor-only) inference, which is safe there because no call_spread row
   * can predate this feature.
   */
  leg_kind: string | null
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
  const refRows = await customerQuery<{
    external_account_ref_ciphertext: string | null
    display_mask: string | null
    brokerage_slug: string | null
  }>(
    `SELECT ba.external_account_ref_ciphertext, ba.display_mask, bc.brokerage_slug
       FROM customer_positions cp
       JOIN broker_accounts ba ON ba.id = cp.broker_account_id
       JOIN brokerage_connections bc ON bc.id = ba.connection_id
      WHERE cp.id = $1`,
    [p.id],
  )
  const refRow = refRows[0] ?? { external_account_ref_ciphertext: null, display_mask: null, brokerage_slug: null }
  const enc = refRow.external_account_ref_ciphertext

  // Same hard invariant as the open path, checked before any close order too: a
  // stray mirrored position sitting in a bot-traded account must never receive a
  // second, uncoordinated close order. FAILS CLOSED and needs a human, not a retry.
  const botGuard = checkCustomerAgainstBotAccounts(refRow)
  if (botGuard.blocked) {
    const detail = describeBotAccountBlock(botGuard)
    await customerExecute(
      `UPDATE customer_positions SET status = 'close_failed', error = $2, updated_at = now() WHERE id = $1`,
      [p.id, `bot_account_guard:${botGuard.reason}`.slice(0, 500)],
    )
    console.error(`[customer-executor] CLOSE BLOCKED for position ${p.id} (user ${p.user_id.slice(0, 8)}): ${detail}`)
    void notifyOps(
      'IronForge: customer CLOSE BLOCKED (bot account guard)',
      `Position ${p.id} (user ${p.user_id.slice(0, 8)}) targets a bot-traded account: ${detail}. ` +
      `No order sent — needs MANUAL review.`,
      true,
    )
    return
  }

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
  const legKind = p.leg_kind ?? (callShort > 0 ? 'condor' : 'put_spread') // pre-leg_kind rows: old inference is safe (see OpenCustomerPosition doc)
  const legs = legKind === 'call_spread'
    ? spreadCloseLegs({ ticker: p.ticker, expiration: exp, short: callShort, long: Number(p.call_long), right: 'C' }, p.contracts)
    : legKind === 'condor'
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
              put_short, put_long, call_short, call_long, contracts, close_attempts, leg_kind
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
              put_short, put_long, call_short, call_long, contracts, close_attempts, close_reason, leg_kind
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
