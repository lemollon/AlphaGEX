import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * api/storage reaches expo-secure-store / react-native, neither of which exists in the
 * node test environment — same reasoning as auth/session.test.ts. A tiny in-memory map
 * stands in for SecureStore/localStorage so the round-trip is real, not stubbed away.
 */
const store = new Map<string, string>()
vi.mock('@/api/storage', () => ({
  setItem: async (key: string, value: string) => {
    store.set(key, value)
  },
  getItem: async (key: string) => store.get(key) ?? null,
  deleteItem: async (key: string) => {
    store.delete(key)
  },
  AFTER_FIRST_UNLOCK: 'AFTER_FIRST_UNLOCK',
}))

const { loadAppearancePreference, saveAppearancePreference, APPEARANCE_STORAGE_KEY } = await import(
  './preference'
)

describe('appearance preference persistence', () => {
  beforeEach(() => {
    store.clear()
  })

  it('loadAppearancePreference() returns null when nothing has ever been saved', async () => {
    expect(await loadAppearancePreference()).toBeNull()
  })

  it('round-trips "light"', async () => {
    await saveAppearancePreference('light')
    expect(await loadAppearancePreference()).toBe('light')
  })

  it('round-trips "dark"', async () => {
    await saveAppearancePreference('dark')
    expect(await loadAppearancePreference()).toBe('dark')
  })

  it('round-trips "system"', async () => {
    await saveAppearancePreference('system')
    expect(await loadAppearancePreference()).toBe('system')
  })

  it('a later save overwrites an earlier one', async () => {
    await saveAppearancePreference('light')
    await saveAppearancePreference('dark')
    expect(await loadAppearancePreference()).toBe('dark')
  })

  it('treats a corrupt/unrecognized stored value as "nothing saved" rather than throwing', async () => {
    store.set(APPEARANCE_STORAGE_KEY, 'not-a-real-preference')
    expect(await loadAppearancePreference()).toBeNull()
  })
})
