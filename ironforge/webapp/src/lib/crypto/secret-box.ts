/**
 * AES-256-GCM encryption for credentials stored at rest (sub-project: brokerage connection).
 *
 * Used to protect the SnapTrade `userSecret` before it lands in the customers DB. The key comes
 * from `SNAPTRADE_SECRET_KEY` (32 bytes, hex or base64). Node `crypto` only — routes run
 * `runtime = 'nodejs'`. Pure given a key; no DB or network.
 *
 * Format of the returned token: `v1.<iv_b64>.<tag_b64>.<ciphertext_b64>` so the IV and auth tag
 * travel with the ciphertext and the scheme is versioned for future rotation.
 */
import { createCipheriv, createDecipheriv, randomBytes } from 'crypto'

const ALG = 'aes-256-gcm'
const VERSION = 'v1'

export class SecretKeyMissingError extends Error {
  constructor() {
    super('SNAPTRADE_SECRET_KEY is not configured')
    this.name = 'SecretKeyMissingError'
  }
}

/** Parse the 32-byte key from env (accepts 64-char hex or base64). Throws if absent/wrong size. */
export function loadSecretKey(raw = process.env.SNAPTRADE_SECRET_KEY): Buffer {
  if (!raw) throw new SecretKeyMissingError()
  const key = /^[0-9a-fA-F]{64}$/.test(raw) ? Buffer.from(raw, 'hex') : Buffer.from(raw, 'base64')
  if (key.length !== 32) {
    throw new Error(`SNAPTRADE_SECRET_KEY must decode to 32 bytes, got ${key.length}`)
  }
  return key
}

export function encryptSecret(plaintext: string, key = loadSecretKey()): string {
  const iv = randomBytes(12)
  const cipher = createCipheriv(ALG, key, iv)
  const ct = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()])
  const tag = cipher.getAuthTag()
  return [VERSION, iv.toString('base64'), tag.toString('base64'), ct.toString('base64')].join('.')
}

export function decryptSecret(token: string, key = loadSecretKey()): string {
  const parts = token.split('.')
  if (parts.length !== 4 || parts[0] !== VERSION) {
    throw new Error('malformed secret token')
  }
  const [, ivB64, tagB64, ctB64] = parts
  const decipher = createDecipheriv(ALG, key, Buffer.from(ivB64, 'base64'))
  decipher.setAuthTag(Buffer.from(tagB64, 'base64'))
  return Buffer.concat([decipher.update(Buffer.from(ctB64, 'base64')), decipher.final()]).toString('utf8')
}
