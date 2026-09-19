/**
 * App Store Server Notifications V2 notificationType -> our subscription status. Pulled out
 * of the /api/billing/apple/notifications route so the state-mapping table is one pure
 * function a test can enumerate directly, instead of something only reachable by POSTing a
 * mocked Apple payload through Next's request machinery.
 *
 * `null` means "no-op": TEST is Apple's own connectivity check (never touches a row), and an
 * unrecognised type is a future notification kind we haven't wired up yet — both ack 200
 * without writing anything, per Apple's retry contract (a non-2xx makes Apple retry
 * indefinitely; there's nothing here retrying would fix).
 */

export type AppleSubscriptionStatus = 'active' | 'canceled' | 'past_due'

export interface StatusForNotificationInput {
  notificationType: string
  /** From the decoded transaction (signedTransactionInfo). */
  expiresDateMs?: number
  revocationDate?: number
  /** From the decoded renewal info (signedRenewalInfo) — set only during a billing retry. */
  gracePeriodExpiresMs?: number
  now?: number
}

export function statusForNotification(input: StatusForNotificationInput): AppleSubscriptionStatus | null {
  const now = input.now ?? Date.now()

  switch (input.notificationType) {
    case 'TEST':
      return null

    // Billing retry failed: 'past_due' while Apple is still in the grace period (the
    // customer keeps access while Apple keeps retrying the card), else the grace period is
    // over and access ends.
    case 'DID_FAIL_TO_RENEW':
      return typeof input.gracePeriodExpiresMs === 'number' && input.gracePeriodExpiresMs > now
        ? 'past_due'
        : 'canceled'

    // Unambiguous terminal states — no need to consult the transaction at all.
    case 'EXPIRED':
    case 'GRACE_PERIOD_EXPIRED':
    case 'REFUND':
    case 'REVOKE':
      return 'canceled'

    // A live/renewed subscription, or a renewal-preference change that doesn't itself end
    // access (turning auto-renew off takes effect at the CURRENT period's expiry, not now).
    // Derive from the transaction's own expiresDate/revocationDate rather than assuming
    // 'active', so a notification that happens to arrive after expiry doesn't resurrect a
    // dead row.
    case 'SUBSCRIBED':
    case 'DID_RENEW':
    case 'DID_CHANGE_RENEWAL_STATUS':
      if (input.revocationDate) return 'canceled'
      return typeof input.expiresDateMs === 'number' && input.expiresDateMs > now ? 'active' : 'canceled'

    default:
      return null
  }
}
