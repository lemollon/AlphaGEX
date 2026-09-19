import { describe, it, expect } from 'vitest'
import { statusForNotification } from '../notification-status'

const NOW = new Date('2026-09-18T12:00:00Z').getTime()
const FUTURE = NOW + 30 * 24 * 60 * 60 * 1000
const PAST = NOW - 60 * 60 * 1000

describe('statusForNotification — the type -> status mapping table', () => {
  const table: Array<[string, Parameters<typeof statusForNotification>[0], ReturnType<typeof statusForNotification>]> = [
    ['TEST', { notificationType: 'TEST', now: NOW }, null],
    ['unrecognised type', { notificationType: 'SOMETHING_NEW_FROM_APPLE', now: NOW }, null],

    ['SUBSCRIBED + future expiry -> active', { notificationType: 'SUBSCRIBED', expiresDateMs: FUTURE, now: NOW }, 'active'],
    ['DID_RENEW + future expiry -> active', { notificationType: 'DID_RENEW', expiresDateMs: FUTURE, now: NOW }, 'active'],
    [
      'DID_CHANGE_RENEWAL_STATUS + future expiry -> active (turning auto-renew off does not end access now)',
      { notificationType: 'DID_CHANGE_RENEWAL_STATUS', expiresDateMs: FUTURE, now: NOW },
      'active',
    ],
    [
      'SUBSCRIBED + past expiry -> canceled (defensive: never resurrect a dead row)',
      { notificationType: 'SUBSCRIBED', expiresDateMs: PAST, now: NOW },
      'canceled',
    ],
    [
      'DID_RENEW + revocationDate set -> canceled even with future expiry',
      { notificationType: 'DID_RENEW', expiresDateMs: FUTURE, revocationDate: NOW - 1000, now: NOW },
      'canceled',
    ],

    ['EXPIRED -> canceled', { notificationType: 'EXPIRED', now: NOW }, 'canceled'],
    ['GRACE_PERIOD_EXPIRED -> canceled', { notificationType: 'GRACE_PERIOD_EXPIRED', now: NOW }, 'canceled'],
    ['REFUND -> canceled', { notificationType: 'REFUND', now: NOW }, 'canceled'],
    ['REVOKE -> canceled', { notificationType: 'REVOKE', now: NOW }, 'canceled'],

    [
      'DID_FAIL_TO_RENEW while still in the grace period -> past_due',
      { notificationType: 'DID_FAIL_TO_RENEW', gracePeriodExpiresMs: FUTURE, now: NOW },
      'past_due',
    ],
    [
      'DID_FAIL_TO_RENEW with no grace period -> canceled',
      { notificationType: 'DID_FAIL_TO_RENEW', now: NOW },
      'canceled',
    ],
    [
      'DID_FAIL_TO_RENEW with an already-expired grace period -> canceled',
      { notificationType: 'DID_FAIL_TO_RENEW', gracePeriodExpiresMs: PAST, now: NOW },
      'canceled',
    ],
  ]

  it.each(table)('%s', (_label, input, expected) => {
    expect(statusForNotification(input)).toBe(expected)
  })
})
