/**
 * Bot Display Names - Biblical Names (Fruits of the Spirit)
 *
 * Maps internal bot codenames to user-facing biblical display names.
 * Based on Galatians 5:22-23 - The Fruits of the Spirit
 *
 * Internal names (Greek mythology) are used in:
 * - API endpoints
 * - Database tables
 * - File/directory names
 * - Code references
 *
 * Display names (Biblical) are used in:
 * - Navigation labels
 * - Page headers
 * - User-facing UI elements
 */

// =============================================================================
// TRADING BOTS - Fruits of the Spirit (Galatians 5:22-23)
// =============================================================================

export const BOT_DISPLAY_NAMES = {
  // Iron Condor Bots
  ARES: 'SELF-CONTROL',      // Iron Condor — disciplined risk management
  PEGASUS: 'PATIENCE',        // Weekly IC — waits for theta decay
  TITAN: 'GOODNESS',          // Aggressive IC — delivers reliable results

  // Directional Bots
  ATHENA: 'FAITHFULNESS',     // Directional — trusts the GEX signals
  ICARUS: 'LOVE',             // Aggressive Directional — bold passion

  // Other Strategies
  PHOENIX: 'JOY',             // 0DTE — daily fresh start, optimism
  ATLAS: 'PEACE',             // Wheel — calm, steady income stream
  HERMES: 'GENTLENESS',       // Manual Wheel — careful human touch
  PROMETHEUS: 'KINDNESS',     // Box Spread Borrowing — provides capital
  HERACLES: 'MEEKNESS',       // MES Futures — controlled strength
} as const

// =============================================================================
// ADVISORY SYSTEMS - Biblical Wisdom Terms
// =============================================================================

export const ADVISOR_DISPLAY_NAMES = {
  ORACLE: 'PROPHET',          // ML Advisory — foretells outcomes
  SAGE: 'WISDOM',             // ML Predictions — divine insight
  ARGUS: 'WATCHMAN',          // 0DTE Gamma — all-seeing vigilance
  ORION: 'STARS',             // GEX ML — heavenly guidance
  GEXIS: 'COUNSELOR',         // AI Assistant — Holy Spirit role
  KRONOS: 'CHRONICLES',       // Backtester — historical record
  HYPERION: 'GLORY',          // Weekly Gamma — radiant vision
  APOLLO: 'DISCERNMENT',      // ML Scanner — spiritual insight
  SOLOMON: 'PROVERBS',        // Feedback Loop — wisdom sayings
  NEXUS: 'COVENANT',          // Neural Network — divine connection
} as const

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

export type BotCodename = keyof typeof BOT_DISPLAY_NAMES
export type AdvisorCodename = keyof typeof ADVISOR_DISPLAY_NAMES

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Get the display name for a trading bot
 * @param codename - The internal codename (e.g., 'ARES')
 * @returns The biblical display name (e.g., 'SELF-CONTROL')
 */
export function getBotDisplayName(codename: string): string {
  const upperCodename = codename.toUpperCase() as BotCodename
  return BOT_DISPLAY_NAMES[upperCodename] || codename
}

/**
 * Get the display name for an advisory system
 * @param codename - The internal codename (e.g., 'ORACLE')
 * @returns The biblical display name (e.g., 'PROPHET')
 */
export function getAdvisorDisplayName(codename: string): string {
  const upperCodename = codename.toUpperCase() as AdvisorCodename
  return ADVISOR_DISPLAY_NAMES[upperCodename] || codename
}

/**
 * Get full display name with strategy description
 * @param codename - The internal codename
 * @param strategy - Optional strategy description to append
 * @returns Formatted display name (e.g., 'SELF-CONTROL (SPY Iron Condor)')
 */
export function getFullDisplayName(codename: string, strategy?: string): string {
  const displayName = getBotDisplayName(codename)
  return strategy ? `${displayName} (${strategy})` : displayName
}

/**
 * Check if a codename is a known bot
 */
export function isKnownBot(codename: string): codename is BotCodename {
  return codename.toUpperCase() in BOT_DISPLAY_NAMES
}

/**
 * Check if a codename is a known advisor
 */
export function isKnownAdvisor(codename: string): codename is AdvisorCodename {
  return codename.toUpperCase() in ADVISOR_DISPLAY_NAMES
}

// =============================================================================
// REVERSE MAPPING (Display Name -> Codename)
// =============================================================================

export const DISPLAY_TO_CODENAME: Record<string, string> = Object.entries(BOT_DISPLAY_NAMES).reduce(
  (acc, [codename, displayName]) => {
    acc[displayName] = codename
    return acc
  },
  {} as Record<string, string>
)

export const ADVISOR_DISPLAY_TO_CODENAME: Record<string, string> = Object.entries(ADVISOR_DISPLAY_NAMES).reduce(
  (acc, [codename, displayName]) => {
    acc[displayName] = codename
    return acc
  },
  {} as Record<string, string>
)
