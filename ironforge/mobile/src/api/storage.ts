/**
 * Token storage. One interface, two implementations chosen by platform.
 *
 * NATIVE (the shipping target) — expo-secure-store, i.e. iOS Keychain / Android
 * Keystore. APP-046 requires tokens encrypted at rest, which is exactly what these
 * provide and what AsyncStorage does not. This path is unchanged and is what runs on
 * every build that reaches a customer.
 *
 * WEB (developer preview only) — localStorage, because a browser has no Keychain.
 * expo-secure-store simply has no web implementation; calling it throws
 * "setValueWithKeyAsync is not a function", which is what blocked the browser preview.
 *
 * ⚠️ The web branch is DELIBERATELY not equivalent in strength, and that is acceptable
 * only because the web bundle is never shipped: `eas build` produces iOS and Android
 * binaries, and app.config.ts declares no web output. It exists so a layout can be
 * eyeballed without a device. If Expo web ever becomes a real distribution target,
 * this branch has to be revisited — localStorage is readable by any script on the
 * origin and would not satisfy APP-046.
 */
import { Platform } from 'react-native'
import * as SecureStore from 'expo-secure-store'

const isWeb = Platform.OS === 'web'

export interface SetOptions {
  /** Native only; ignored on web, which has no equivalent concept. */
  keychainAccessible?: (typeof SecureStore)['AFTER_FIRST_UNLOCK']
}

export async function setItem(key: string, value: string, opts?: SetOptions): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.setItem(key, value)
    return
  }
  await SecureStore.setItemAsync(key, value, opts)
}

export async function getItem(key: string): Promise<string | null> {
  if (isWeb) return globalThis.localStorage?.getItem(key) ?? null
  return SecureStore.getItemAsync(key)
}

export async function deleteItem(key: string): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.removeItem(key)
    return
  }
  await SecureStore.deleteItemAsync(key)
}

export const AFTER_FIRST_UNLOCK = SecureStore.AFTER_FIRST_UNLOCK
