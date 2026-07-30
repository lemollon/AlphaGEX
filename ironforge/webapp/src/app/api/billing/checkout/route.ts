import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import {
  isStripeConfigured,
  findPriceIdByLookupKey,
  getOrCreateCustomer,
  createCustomer,
  createSubscriptionCheckout,
  createSetupCheckout,
  isMissingCustomerError,
  retrieveSubscription,
  upgradeSubscriptionToBundle,
} from '@/lib/billing/stripe'
import {
  getBotPlan,
  otherBotSlug,
  BOTH_PLAN,
  TRIAL_DAYS,
  COMMUNITY_KEY,
  COMMUNITY_PLAN,
  isCommunityKey,
} from '@/lib/billing/plans'
import { getEnrollmentForUser } from '@/lib/enrollment/service'
import { isAutomatePlan } from '@/lib/enrollment/legal'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Starts a Stripe Checkout session for a bot subscription. Customer-session-guarded. Looks up (or
 * creates) the customer's Stripe Customer, resolves the bot's Price by lookup key, and returns the
 * hosted Checkout url. The card is entered on Stripe — never on IronForge. Returns 503 until Stripe
 * is provisioned so the Open Account page degrades cleanly.
 */

interface UserRow {
  id: string
  email: string | null
  stripe_customer_id: string | null
}

export async function POST(req: NextRequest) {
  const session = await getCustomerSession()
  if (!session.customerId) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  let bot: string | undefined
  let intent: string | undefined
  let enrollmentId: string | undefined
  let returnTo: string | undefined
  try {
    const body = (await req.json().catch(() => null)) as {
      bot?: unknown
      intent?: unknown
      enrollment_id?: unknown
      return_to?: unknown
    } | null
    if (body && typeof body.bot === 'string') bot = body.bot
    if (body && typeof body.intent === 'string') intent = body.intent
    if (body && typeof body.enrollment_id === 'string') enrollmentId = body.enrollment_id
    // Allowlisted literal, never a URL — the only alternate return surface is /enroll.
    if (body && body.return_to === 'enroll') returnTo = 'enroll'
  } catch {
    /* fall through to validation */
  }

  // ── Enrollment funnel, automate family: setup-mode checkout ($0 due today) ──────
  // Requested EXPLICITLY by the /enroll billing step, validated server-side against an
  // owned enrollment in billing_pending with an automate-family plan. This is what lets
  // the v2 funnel collect a card at $0 while IRONFORGE_ENROLLMENT_V2 stays off — that
  // flag remains solely the legacy /live/[bot]/open cutover switch below. No bot is
  // involved yet (the agent is chosen at AGENT-01); the subscription is created only by
  // POST /api/v1/activations.
  const isEnrollmentSetup = intent === 'enrollment_setup'

  // Community is a standalone chat/education plan, not a trading bot — it takes its own
  // simple path (no bundle logic, no trial). Everything else must resolve to a real bot.
  const isCommunity = isCommunityKey(bot)
  if (!isEnrollmentSetup && !isCommunity && !getBotPlan(bot)) {
    return NextResponse.json({ ok: false, error: 'Unknown bot.' }, { status: 400 })
  }

  if (!isStripeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Checkout is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  try {
    const rows = await customerQuery<UserRow>(
      `SELECT id, email, stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
      [session.customerId],
    )
    const user = rows[0]
    if (!user) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

    // Persist the resolved Stripe customer id when it changes (new or self-healed).
    const persistCustomer = async (id: string) => {
      if (id !== user.stripe_customer_id) {
        await customerExecute(`UPDATE users SET stripe_customer_id = $2, updated_at = now() WHERE id = $1`, [user.id, id])
      }
    }

    // ── Enrollment funnel: setup-mode checkout, $0 due today, card only ─────────────
    if (isEnrollmentSetup) {
      const origin = publicOrigin(req)
      const enrollment = enrollmentId ? await getEnrollmentForUser(enrollmentId, user.id) : null
      if (!enrollment) {
        return NextResponse.json({ ok: false, error: 'That enrollment is not available.' }, { status: 403 })
      }
      // Only the state the funnel is actually in may mint a $0 session: billing_pending
      // on an automate-family plan. Anything else (community, already past billing, a
      // guessed id) is refused — this branch must never be a discount door to a bot plan.
      if (enrollment.status !== 'billing_pending' || !isAutomatePlan(enrollment.selected_plan)) {
        return NextResponse.json({ ok: false, error: 'Billing is not the current step for this enrollment.' }, { status: 409 })
      }

      const setupArgs = {
        userId: user.id,
        enrollmentId: enrollment.id,
        successUrl: `${origin}/enroll/billing?checkout=success&session_id={CHECKOUT_SESSION_ID}`,
        cancelUrl: `${origin}/enroll/billing?checkout=canceled`,
      }

      let setupCustomerId = await getOrCreateCustomer({
        existingId: user.stripe_customer_id,
        email: user.email,
        userId: user.id,
      })
      await persistCustomer(setupCustomerId)

      let setupUrl: string
      try {
        ;({ url: setupUrl } = await createSetupCheckout({ customerId: setupCustomerId, ...setupArgs }))
      } catch (e) {
        if (!isMissingCustomerError(e)) throw e
        setupCustomerId = await createCustomer({ email: user.email, userId: user.id })
        await persistCustomer(setupCustomerId)
        ;({ url: setupUrl } = await createSetupCheckout({ customerId: setupCustomerId, ...setupArgs }))
      }

      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CHECKOUT_STARTED', $2)`,
        [user.id, JSON.stringify({ mode: 'setup', enrollment_id: enrollment.id })],
      ).catch(() => {})

      return NextResponse.json({ ok: true, url: setupUrl })
    }

    // ── Community: standalone $15 chat/education plan, no bot, no bundle, no trial ──
    if (isCommunity) {
      const origin = publicOrigin(req)
      const existing = await customerQuery<{ status: string }>(
        `SELECT status FROM customer_bot_subscriptions WHERE user_id = $1 AND bot = $2 LIMIT 1`,
        [user.id, COMMUNITY_KEY],
      )
      // Already a member → idempotent, just send them into the community (or the
      // enrollment completion page when the funnel initiated this).
      if (existing.some((s) => ['trialing', 'active', 'past_due'].includes(s.status))) {
        return NextResponse.json({
          ok: true,
          url: returnTo === 'enroll' ? `${origin}/enroll/done?welcome=community` : `${origin}/community?welcome=community`,
        })
      }

      const communityPriceId = await findPriceIdByLookupKey(COMMUNITY_PLAN.lookupKey)
      if (!communityPriceId) {
        return NextResponse.json(
          { ok: false, error: 'Community isn’t available yet. Please try again shortly.' },
          { status: 503 },
        )
      }

      const communityArgs = {
        priceId: communityPriceId,
        userId: user.id,
        bot: COMMUNITY_KEY,
        trialDays: 0, // charge immediately — it's a low-cost access plan, not a strategy trial
        // The /enroll funnel returns to its own completion/billing pages so the
        // server-owned enrollment can advance; the legacy join button keeps /community.
        successUrl:
          returnTo === 'enroll'
            ? `${origin}/enroll/done?welcome=community&session_id={CHECKOUT_SESSION_ID}`
            : `${origin}/community?welcome=community&session_id={CHECKOUT_SESSION_ID}`,
        // Back to where the join button is. The legacy path pointed at /pricing once,
        // which has 308'd to /#memberships since the pricing page was retired — so
        // abandoning checkout threw a signed-in customer out to the marketing homepage
        // AND dropped the ?canceled flag on the redirect.
        cancelUrl:
          returnTo === 'enroll'
            ? `${origin}/enroll/billing?checkout=canceled`
            : `${origin}/community?canceled=community`,
      }

      let communityCustomerId = await getOrCreateCustomer({
        existingId: user.stripe_customer_id,
        email: user.email,
        userId: user.id,
      })
      await persistCustomer(communityCustomerId)

      let communityUrl: string
      try {
        ;({ url: communityUrl } = await createSubscriptionCheckout({ customerId: communityCustomerId, ...communityArgs }))
      } catch (e) {
        if (!isMissingCustomerError(e)) throw e
        communityCustomerId = await createCustomer({ email: user.email, userId: user.id })
        await persistCustomer(communityCustomerId)
        ;({ url: communityUrl } = await createSubscriptionCheckout({ customerId: communityCustomerId, ...communityArgs }))
      }

      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CHECKOUT_STARTED', $2)`,
        [user.id, JSON.stringify({ bot: COMMUNITY_KEY })],
      ).catch(() => {})

      return NextResponse.json({ ok: true, url: communityUrl })
    }

    // Non-community: guaranteed a real bot by the top-of-handler validation.
    const plan = getBotPlan(bot)!

    // ── Second bot = bundle upgrade, not a second $50 subscription ──────────────
    // If this customer already has an active/trialing subscription to the OTHER bot,
    // opening this one lifts that subscription to the two-bot bundle ($75) instead of
    // adding a full second bot ($50). The increment is $25 (both − single), the card is
    // already on file, so there is no second Checkout — we modify the existing sub and
    // return straight to the Live page.
    const LIVE_STATUSES = ['trialing', 'active', 'past_due']
    const existingSubs = await customerQuery<{
      bot: string
      status: string
      stripe_subscription_id: string | null
    }>(
      `SELECT bot, status, stripe_subscription_id FROM customer_bot_subscriptions WHERE user_id = $1`,
      [user.id],
    )
    const activeSubs = existingSubs.filter((s) => LIVE_STATUSES.includes(s.status))
    const origin = publicOrigin(req)

    // Already own this exact bot → idempotent, just send them to it.
    if (activeSubs.some((s) => s.bot === plan.slug)) {
      return NextResponse.json({ ok: true, url: `${origin}${plan.liveHref}?welcome=${plan.slug}` })
    }

    const other = otherBotSlug(plan.slug)
    const otherSub = activeSubs.find((s) => s.bot === other && s.stripe_subscription_id)
    if (otherSub?.stripe_subscription_id) {
      const bundlePriceId = await findPriceIdByLookupKey(BOTH_PLAN.lookupKey)
      if (!bundlePriceId) {
        return NextResponse.json(
          { ok: false, error: 'The two-bot bundle isn’t available yet. Please try again shortly.' },
          { status: 503 },
        )
      }
      const sub = await retrieveSubscription(otherSub.stripe_subscription_id)
      const itemId = sub.items?.data?.[0]?.id
      if (!itemId) throw new Error('subscription has no line item to upgrade')

      const updated = await upgradeSubscriptionToBundle({
        subscriptionId: sub.id,
        itemId,
        bundlePriceId,
        userId: user.id,
        bots: `${plan.slug},${other}`,
      })
      const periodEnd =
        typeof updated.current_period_end === 'number' && updated.current_period_end > 0
          ? new Date(updated.current_period_end * 1000).toISOString()
          : null
      const status = updated.status || otherSub.status

      // Grant BOTH bot entitlements from the one bundle subscription. (The webhook will
      // reconcile the same rows when the subscription.updated event arrives — this write
      // makes the Live page correct immediately without waiting on it.)
      for (const b of [plan.slug, other]) {
        await customerExecute(
          `INSERT INTO customer_bot_subscriptions
             (user_id, bot, status, stripe_subscription_id, price_lookup_key, current_period_end, updated_at)
           VALUES ($1, $2, $3, $4, $5, $6, now())
           ON CONFLICT (user_id, bot) DO UPDATE SET
             status = EXCLUDED.status,
             stripe_subscription_id = EXCLUDED.stripe_subscription_id,
             price_lookup_key = EXCLUDED.price_lookup_key,
             current_period_end = EXCLUDED.current_period_end,
             updated_at = now()`,
          [user.id, b, status, sub.id, BOTH_PLAN.lookupKey, periodEnd],
        )
      }
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BUNDLE_UPGRADE', $2)`,
        [user.id, JSON.stringify({ added: plan.slug, subscription: sub.id })],
      ).catch(() => {})

      return NextResponse.json({ ok: true, url: `${origin}${plan.liveHref}?welcome=${plan.slug}` })
    }
    // ────────────────────────────────────────────────────────────────────────────

    const priceId = await findPriceIdByLookupKey(plan.lookupKey)
    if (!priceId) {
      // Keys set but products not created yet — treat as not-yet-available, not a hard error.
      return NextResponse.json(
        { ok: false, error: 'This plan isn’t available yet. Please try again shortly.' },
        { status: 503 },
      )
    }

    const checkoutArgs = {
      priceId,
      userId: user.id,
      bot: plan.slug,
      trialDays: TRIAL_DAYS,
      successUrl: `${origin}${plan.liveHref}?welcome=${plan.slug}&session_id={CHECKOUT_SESSION_ID}`,
      cancelUrl: `${origin}/live/${plan.slug}/open?canceled=1`,
    }

    let customerId = await getOrCreateCustomer({
      existingId: user.stripe_customer_id,
      email: user.email,
      userId: user.id,
    })
    await persistCustomer(customerId)

    // ── Enrollment v2 (spec §7): collect the card at $0 DUE, subscribe at ACTIVATION ──
    //
    // v1 (default): subscription-mode checkout with Stripe trial_period_days = 5. That
    // starts a CALENDAR trial the moment the card is captured — exactly what §7 forbids
    // ("Do not start the trial clock at card capture"), and a weekend plus a holiday can
    // eat most of it before the customer sees a single trade.
    //
    // v2: setup-mode checkout ($0 due today). No subscription exists until
    // POST /api/v1/activations creates it in `trialing`, and the trading-day ledger ends
    // that trial after five ELIGIBLE days.
    //
    // FLAGGED, DEFAULT OFF. This is a live money path with Stripe already provisioned;
    // flipping it changes what every new Automate customer is charged and when. It ships
    // dark so the switch is a deliberate, reversible act rather than a deploy.
    const enrollmentV2 = process.env.IRONFORGE_ENROLLMENT_V2 === 'true'

    let url: string
    const startCheckout = async (cid: string): Promise<{ url: string }> =>
      enrollmentV2
        ? createSetupCheckout({
            customerId: cid,
            userId: checkoutArgs.userId,
            bot: checkoutArgs.bot,
            successUrl: checkoutArgs.successUrl,
            cancelUrl: checkoutArgs.cancelUrl,
          })
        : createSubscriptionCheckout({ customerId: cid, ...checkoutArgs })

    try {
      ;({ url } = await startCheckout(customerId))
    } catch (e) {
      // Self-heal a stale stored customer id (wrong Stripe mode, or deleted in the dashboard):
      // mint a fresh customer, persist it, and retry once.
      if (!isMissingCustomerError(e)) throw e
      console.warn('[billing/checkout] stale customer', customerId, '- recreating for user', user.id)
      customerId = await createCustomer({ email: user.email, userId: user.id })
      await persistCustomer(customerId)
      ;({ url } = await startCheckout(customerId))
    }

    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'CHECKOUT_STARTED', $2)`,
      [user.id, JSON.stringify({ bot: plan.slug, mode: enrollmentV2 ? 'setup' : 'subscription' })],
    ).catch(() => {})

    return NextResponse.json({ ok: true, url })
  } catch (e) {
    console.error('[billing/checkout] failed:', e)
    return NextResponse.json({ ok: false, error: 'Could not start checkout. Please try again.' }, { status: 500 })
  }
}
