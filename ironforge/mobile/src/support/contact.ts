/**
 * Email Support (APP-043).
 *
 * The draft carries a non-sensitive diagnostic reference — app version, build, platform
 * and OS. Deliberately nothing else: no customer id, no email, no account number, no
 * balance. A support draft is a message the customer can forward anywhere, so it must
 * not contain anything that would matter if they did.
 *
 * ⚠️ support@ironforge.trade is still NOT a real mailbox. It is the address the approved
 * spec names and the one already published on /contact and /delete-account, so the app
 * stays consistent with the rest of the product — but until the alias exists these mails
 * go nowhere. Creating it needs a Workspace admin.
 */
import { Platform } from 'react-native'
import Constants from 'expo-constants'

export const SUPPORT_EMAIL = 'support@ironforge.trade'

export function diagnosticReference(): string {
  const version = Constants.expoConfig?.version ?? 'unknown'
  const build =
    Platform.OS === 'ios'
      ? (Constants.expoConfig?.ios?.buildNumber ?? '—')
      : String(Constants.expoConfig?.android?.versionCode ?? '—')
  return `IronForge ${version} (${build}) · ${Platform.OS} ${String(Platform.Version)}`
}

/** A prefilled draft to support, with the diagnostic footer already in the body. */
export function supportMailto(subject = 'IronForge support request'): string {
  const body = `\n\n\n—\n${diagnosticReference()}`
  return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}
