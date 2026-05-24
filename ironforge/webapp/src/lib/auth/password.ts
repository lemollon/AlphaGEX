import bcrypt from 'bcryptjs'

const ROUNDS = 10

export async function hashPassword(plain: string): Promise<string> {
  return bcrypt.hash(plain, ROUNDS)
}

export async function verifyPassword(plain: string, hash: string): Promise<boolean> {
  if (!hash) return false
  return bcrypt.compare(plain, hash)
}
