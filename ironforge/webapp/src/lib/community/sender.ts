import type { CommunitySenderType } from '@ironforge/shared/api-types'

/**
 * Pure sender-type logic (#248), split out of store.ts deliberately: store.ts
 * pulls in the whole server-side data layer (customers-db, forge-ai, and
 * transitively next/headers via lib/tradier → lib/scanner → lib/live/*), which
 * is fine for server code but poisons any client component that imports a
 * real (non-type-only) value from it — CommunityClient.tsx needs isAiSender()
 * at render time, not just the types, so it imports this file instead.
 */

// `SenderType` keeps its pre-#225 name here even though the shared module
// calls it `CommunitySenderType` (mobile's api/types.ts does the same rename).
export type SenderType = CommunitySenderType

/**
 * Whether a post/reply was authored by an AI persona rather than a member (#248).
 * New rows carry the typed sender_type directly — no string-sniffing. Old rows
 * (pre-migration 'FORGE'/'SYSTEM') render exactly as they always did.
 */
export function isAiSender(senderType: string): boolean {
  return senderType === 'FORGE' || senderType === 'SYSTEM' || senderType === 'sparky' || senderType === 'flame_ai'
}

/**
 * Whether a post was authored specifically by Sparky rather than the generic
 * Forge AI. Typed rows answer this directly; untyped/legacy rows fall back to
 * the old name-substring heuristic so they keep rendering as before.
 */
export function isSparkySender(message: { sender_type: string; sender_name: string }): boolean {
  if (message.sender_type === 'sparky') return true
  if (message.sender_type === 'flame_ai' || message.sender_type === 'FORGE' || message.sender_type === 'SYSTEM') {
    return false
  }
  return message.sender_name.toLowerCase().includes('sparky')
}
