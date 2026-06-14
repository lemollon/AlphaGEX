import { describe, it, expect } from 'vitest'
import { encryptSecret, decryptSecret, loadSecretKey, SecretKeyMissingError } from '@/lib/crypto/secret-box'
import { randomBytes } from 'crypto'

const KEY = randomBytes(32) // raw 32-byte key, bypasses env

describe('secret-box (AES-256-GCM)', () => {
  it('round-trips a secret', () => {
    const token = encryptSecret('user-secret-abc123', KEY)
    expect(decryptSecret(token, KEY)).toBe('user-secret-abc123')
  })

  it('produces a versioned 4-part token and never the plaintext', () => {
    const token = encryptSecret('plaintext-value', KEY)
    expect(token.split('.')).toHaveLength(4)
    expect(token.startsWith('v1.')).toBe(true)
    expect(token).not.toContain('plaintext-value')
  })

  it('uses a fresh IV each call (ciphertext differs for same input)', () => {
    expect(encryptSecret('same', KEY)).not.toBe(encryptSecret('same', KEY))
  })

  it('fails to decrypt if the auth tag/ciphertext is tampered with', () => {
    const token = encryptSecret('tamper-me', KEY)
    const parts = token.split('.')
    parts[3] = Buffer.from('totally-different').toString('base64')
    expect(() => decryptSecret(parts.join('.'), KEY)).toThrow()
  })

  it('rejects a malformed token', () => {
    expect(() => decryptSecret('not-a-valid-token', KEY)).toThrow(/malformed/)
  })

  it('loadSecretKey accepts hex and base64 and rejects wrong sizes', () => {
    expect(loadSecretKey('a'.repeat(64)).length).toBe(32) // 64 hex chars → 32 bytes
    expect(loadSecretKey(KEY.toString('base64')).length).toBe(32)
    expect(() => loadSecretKey('short')).toThrow()
    expect(() => loadSecretKey(undefined)).toThrow(SecretKeyMissingError)
  })
})
