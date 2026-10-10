/**
 * Appearance preference persistence — reuses `@/api/storage` (SecureStore on native,
 * localStorage in the web dev preview), the same one-interface storage every other
 * persisted preference in this app goes through (see auth/session.ts). No new
 * dependency: AsyncStorage was never installed and isn't needed here.
 */
import { getItem, setItem } from '@/api/storage'
import type { AppearancePreference } from './palette'

export const APPEARANCE_STORAGE_KEY = 'ironforge.appearance'

function isAppearancePreference(v: string | null): v is AppearancePreference {
  return v === 'system' || v === 'light' || v === 'dark'
}

/**
 * `null` means "nothing saved yet" — per #222 the caller defaults that to 'system'
 * (follow the OS), not 'dark'. A customer who already has an actual saved choice —
 * 'system', 'light', or 'dark' — always gets exactly that back; this only changes
 * what a customer who has never touched the appearance setting sees.
 */
export async function loadAppearancePreference(): Promise<AppearancePreference | null> {
  const stored = await getItem(APPEARANCE_STORAGE_KEY)
  return isAppearancePreference(stored) ? stored : null
}

export async function saveAppearancePreference(pref: AppearancePreference): Promise<void> {
  await setItem(APPEARANCE_STORAGE_KEY, pref)
}
