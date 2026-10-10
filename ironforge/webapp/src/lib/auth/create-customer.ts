/**
 * Shared customer-account creation (sub-project C, extended for Google SSO).
 *
 * Both POST /api/auth/signup (password + full KYC form) and GET
 * /api/auth/google/callback (OAuth, no password, profile from Google) create the
 * SAME users row — same columns, same audit trail, same CRM/Attio side effects —
 * so the two signup paths can never drift into two different answers for "what is
 * an IronForge account." This is that one function; both routes call it.
 */

import { generateToken, TOKEN_TTL_MS, generateCode, hashCode, CODE_TTL_MS } from '@/lib/auth/verification-token'
import { sendVerificationEmail } from '@/lib/email'
import { syncContactToAttio, enqueueAttioSync } from '@/lib/attio'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { customerExecute, customerTransaction } from '@/lib/customers-db'

export function clientIpFromHeaders(xff: string | null): string | null {
  return xff ? xff.split(',')[0].trim() : null
}

export function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!domain) return '***'
  return `${local.slice(0, 1)}***@${domain}`
}

export async function writeAudit(
  userId: string | null,
  eventType: string,
  ip: string | null,
  ua: string | null,
  metadata: Record<string, unknown>,
): Promise<void> {
  // Best-effort: audit failures must never block the user (doc §5).
  try {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
       VALUES ($1, $2, $3, $4, $5)`,
      [userId, eventType, ip, ua, JSON.stringify(metadata)],
    )
  } catch (e) {
    console.error('[create-customer] audit write failed:', eventType, e)
  }
}

export type AuthProvider = 'password' | 'google'

export interface CreateCustomerAccountInput {
  firstName: string
  lastName: string
  username: string
  /** Already normalized (trimmed, lowercased) by the caller. */
  email: string
  /** Null for a Google account that was never asked for one. */
  phone: string | null
  /** Null for a Google account that was never asked for one. */
  state: string | null
  /** Null for an SSO account — there is no password to hash. */
  passwordHash: string | null
  authProvider: AuthProvider
  /** `${provider}:${sub}`, e.g. 'google:1234567890'. Null for password accounts. */
  authUserId: string | null
  referralCode: string | null
  promoCode: string | null
  intendedPlan: 'community' | 'automate' | null
  ageConfirmed: boolean
  noAdviceAcknowledged: boolean
  electronicCommConsent: boolean
  /** Google's email_verified claim is already a real verification — skip our own link/code. */
  emailVerified: boolean
  ip: string | null
  userAgent: string | null
  /** Audit/CRM provenance, e.g. 'signup' | 'google_signup'. */
  source: string
  /**
   * Base URL for the verification email's link. Pass null to skip sending — only
   * meaningful when `emailVerified` is false; a Google account never needs this.
   */
  publicOrigin: string | null
}

export interface CreateCustomerAccountResult {
  userId: string
  /** Present only when `emailVerified` was false — the route's own dev-mode echo. */
  verifyToken?: string
  verifyCode?: string
}

export async function createCustomerAccount(
  input: CreateCustomerAccountInput,
): Promise<CreateCustomerAccountResult> {
  const needsVerification = !input.emailVerified
  const { raw: rawToken, hash: tokenHash } = generateToken()
  const expiresAt = new Date(Date.now() + TOKEN_TTL_MS).toISOString()
  const code = generateCode()
  const codeExpiresAt = new Date(Date.now() + CODE_TTL_MS).toISOString()

  const userId = await customerTransaction<string>(async (run) => {
    const rows = await run(
      `INSERT INTO users
         (password_hash, first_name, last_name, username, email, phone, state, referral_code, promo_code,
          age_confirmed, no_advice_acknowledged, electronic_comm_consent, intended_plan,
          auth_provider, auth_user_id, email_verified)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
       RETURNING id`,
      [
        input.passwordHash,
        input.firstName,
        input.lastName,
        input.username,
        input.email,
        input.phone,
        input.state,
        input.referralCode,
        input.promoCode,
        input.ageConfirmed,
        input.noAdviceAcknowledged,
        input.electronicCommConsent,
        input.intendedPlan,
        input.authProvider,
        input.authUserId,
        input.emailVerified,
      ],
    )
    const uid = rows[0].id as string
    if (needsVerification) {
      // code_hash is salted with uid (hashCode), so it must be computed after the
      // INSERT ... RETURNING id above, not before.
      await run(
        `INSERT INTO email_verification_tokens (user_id, token_hash, expires_at, code_hash, code_expires_at)
         VALUES ($1,$2,$3,$4,$5)`,
        [uid, tokenHash, expiresAt, hashCode(code, uid), codeExpiresAt],
      )
    }
    return uid
  })

  // UAT-007 (account isolation): a successful signup must never leave the browser
  // authenticated as a PREVIOUS user. Without this, a stale customer cookie from an
  // earlier login rode along and every subsequent page resolved the OLD account.
  const staleSession = await getCustomerSession()
  if (staleSession.customerId) staleSession.destroy()

  await writeAudit(userId, 'ACCOUNT_CREATED', input.ip, input.userAgent, {
    source: input.source,
    state: input.state,
    referral_code: input.referralCode,
    promo_code: input.promoCode,
    age_confirmed: input.ageConfirmed,
    no_advice_acknowledged: input.noAdviceAcknowledged,
    electronic_comm_consent: input.electronicCommConsent,
    auth_provider: input.authProvider,
  })

  // Send the verification email (non-blocking: failure never blocks the account).
  // Never applies to a Google account — its email is already verified.
  if (needsVerification && input.publicOrigin) {
    const verifyUrl = `${input.publicOrigin}/api/auth/verify?token=${encodeURIComponent(rawToken)}`
    try {
      const emailRes = await sendVerificationEmail({
        to: input.email,
        verifyUrl,
        firstName: input.firstName,
        code,
      })
      if (emailRes.sent) {
        await writeAudit(userId, 'EMAIL_VERIFICATION_SENT', input.ip, input.userAgent, {
          email_masked: maskEmail(input.email),
        })
      } else if (emailRes.skipped) {
        console.warn(
          '[create-customer] verification email SKIPPED (RESEND_API_KEY/EMAIL_FROM unset) for',
          maskEmail(input.email),
        )
      } else if (emailRes.error) {
        console.error('[create-customer] verification email failed:', emailRes.error)
      }
    } catch (e) {
      console.error('[create-customer] verification email threw:', e)
    }
  }

  // Sub-project E: mirror the prospect into Attio CRM (best-effort; never blocks
  // the account). On failure, queue for retry + record an ATTIO_SYNC_FAILED audit.
  try {
    const contact = {
      firstName: input.firstName,
      lastName: input.lastName,
      email: input.email,
      phone: input.phone ?? '',
      state: input.state ?? undefined,
      referralCode: input.referralCode ?? undefined,
    }
    const attioRes = await syncContactToAttio(contact)
    if (attioRes.synced) {
      await writeAudit(userId, 'ATTIO_SYNCED', input.ip, input.userAgent, {
        record_id: attioRes.recordId ?? null,
      })
    } else if (!attioRes.skipped) {
      await enqueueAttioSync(userId, contact, attioRes.error ?? 'unknown')
      await writeAudit(userId, 'ATTIO_SYNC_FAILED', input.ip, input.userAgent, {
        error: (attioRes.error ?? '').slice(0, 200),
      })
    }
  } catch (e) {
    console.error('[create-customer] attio sync threw:', e)
  }

  // CRM: account created. Queued, so it survives an Attio outage; the legacy sync
  // above only ever wrote name/email/phone as a Note.
  await enqueueCrmEvent({
    eventId: `acct_${userId}`,
    eventType: 'crm.account_created',
    userId,
    payload: {
      email: input.email,
      firstName: input.firstName,
      lastName: input.lastName,
      phone: input.phone ?? '',
      ironforgeUserId: userId,
    },
  })

  return {
    userId,
    verifyToken: needsVerification ? rawToken : undefined,
    verifyCode: needsVerification ? code : undefined,
  }
}
