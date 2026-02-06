/**
 * Bot Display Names - Biblical Names with Scripture References
 *
 * Maps internal bot codenames to user-facing biblical display names.
 * Each name is chosen to reflect the bot's trading character and strategy.
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
// BOT SCRIPTURE REFERENCES
// =============================================================================
// Each bot has a biblical name with verse reference and explanation

export interface BotScripture {
  displayName: string
  verse: string
  reference: string
  why: string
}

export const BOT_SCRIPTURES: Record<string, BotScripture> = {
  // ─────────────────────────────────────────────────────────────────────────────
  // ARES → FORTRESS (SPY Iron Condor - Defensive, Protects Capital)
  // ─────────────────────────────────────────────────────────────────────────────
  ARES: {
    displayName: 'FORTRESS',
    verse: '"The LORD is my rock, my fortress and my deliverer; my God is my rock, in whom I take refuge, my shield and the horn of my salvation, my stronghold."',
    reference: 'Psalm 18:2',
    why: 'Iron Condors are defensive positions that protect capital like a fortress protects those within. The strategy creates walls (short strikes) that shield against market movement.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // ATHENA → SOLOMON (Directional Spreads - Wisdom, Strategic Decisions)
  // ─────────────────────────────────────────────────────────────────────────────
  ATHENA: {
    displayName: 'SOLOMON',
    verse: '"God gave Solomon wisdom and very great insight, and a breadth of understanding as measureless as the sand on the seashore."',
    reference: '1 Kings 4:29 (see also 1 Kings 3:5-14)',
    why: 'Directional trading requires wisdom to discern market direction. Like Solomon who asked God for wisdom to lead, this bot uses GEX signals to make wise directional decisions.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // ICARUS → GIDEON (Aggressive Directional - Bold Warrior, Takes Risks)
  // ─────────────────────────────────────────────────────────────────────────────
  ICARUS: {
    displayName: 'GIDEON',
    verse: '"The LORD turned to him and said, \'Go in the strength you have and save Israel out of Midian\'s hand. Am I not sending you?\'"',
    reference: 'Judges 6:14 (see Judges 6-8)',
    why: 'Gideon defeated a vast army with just 300 men—bold, aggressive action with calculated risk. This bot takes aggressive directional positions when signals are strong, trusting the strategy even when it seems risky.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // PEGASUS → ANCHOR (SPX Weekly IC - Steady, Holds Firm, Patient)
  // ─────────────────────────────────────────────────────────────────────────────
  PEGASUS: {
    displayName: 'ANCHOR',
    verse: '"We have this hope as an anchor for the soul, firm and secure."',
    reference: 'Hebrews 6:19',
    why: 'Weekly Iron Condors require patience—waiting for theta decay while staying anchored to the position. Like an anchor holds a ship steady through waves, this bot holds firm through market volatility.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // TITAN → SAMSON (Aggressive SPX IC - Raw Power, Aggressive Strength)
  // ─────────────────────────────────────────────────────────────────────────────
  TITAN: {
    displayName: 'SAMSON',
    verse: '"Then Samson prayed to the LORD, \'Sovereign LORD, remember me. Please, God, strengthen me just once more.\'"',
    reference: 'Judges 16:28 (see Judges 13-16)',
    why: 'Samson was given supernatural strength for bold acts. This aggressive SPX Iron Condor bot uses higher risk parameters (15% vs 10%) and tighter strikes for more powerful premium collection.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // PHOENIX → LAZARUS (0DTE Momentum - Resurrection, Daily Renewal)
  // ─────────────────────────────────────────────────────────────────────────────
  PHOENIX: {
    displayName: 'LAZARUS',
    verse: '"Jesus called in a loud voice, \'Lazarus, come out!\' The dead man came out."',
    reference: 'John 11:43-44 (see John 11:1-44)',
    why: 'Lazarus was raised from the dead—the ultimate comeback story. 0DTE positions expire daily and are "reborn" each morning. Every trading day is a resurrection, a fresh start.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // ATLAS → CORNERSTONE (SPX Wheel - Foundation, Steady Support)
  // ─────────────────────────────────────────────────────────────────────────────
  ATLAS: {
    displayName: 'CORNERSTONE',
    verse: '"The stone the builders rejected has become the cornerstone; the LORD has done this, and it is marvelous in our eyes."',
    reference: 'Psalm 118:22 (quoted in Matthew 21:42)',
    why: 'The wheel strategy is foundational—a cornerstone of options income. It provides steady, reliable returns that support the broader portfolio, just as a cornerstone supports an entire building.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // HERMES → SHEPHERD (Manual Wheel - Careful Tending, Personal Attention)
  // ─────────────────────────────────────────────────────────────────────────────
  HERMES: {
    displayName: 'SHEPHERD',
    verse: '"The LORD is my shepherd, I lack nothing. He makes me lie down in green pastures, he leads me beside quiet waters."',
    reference: 'Psalm 23:1-2 (see Psalm 23, John 10:11-18)',
    why: 'A shepherd personally tends each sheep with care. This manual wheel strategy requires hands-on attention, carefully guiding each position like a shepherd guides the flock.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // PROMETHEUS → JUBILEE (Box Spread Borrowing - Debt Freedom, Provision)
  // ─────────────────────────────────────────────────────────────────────────────
  PROMETHEUS: {
    displayName: 'JUBILEE',
    verse: '"Consecrate the fiftieth year and proclaim liberty throughout the land to all its inhabitants. It shall be a jubilee for you."',
    reference: 'Leviticus 25:10 (see Leviticus 25:8-55)',
    why: 'The Year of Jubilee was when all debts were cancelled and financial freedom proclaimed. Box spreads provide synthetic borrowing at favorable rates—financial leverage that enables freedom to trade.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // HERACLES → VALOR (MES Futures Scalping - Courage, Strength)
  // ─────────────────────────────────────────────────────────────────────────────
  HERACLES: {
    displayName: 'VALOR',
    verse: '"Have I not commanded you? Be strong and courageous. Do not be afraid; do not be discouraged, for the LORD your God will be with you wherever you go."',
    reference: 'Joshua 1:9',
    why: 'Futures scalping requires courage—quick decisions in fast-moving markets. Like Joshua leading Israel into battle, this bot enters and exits positions with valor and conviction.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE → AGAPE (ETH Micro Futures - Unconditional Love, Steadfast Devotion)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE: {
    displayName: 'AGAPE',
    verse: '"Love is patient, love is kind. It does not envy, it does not boast, it is not proud. It always protects, always trusts, always hopes, always perseveres."',
    reference: '1 Corinthians 13:4,7',
    why: 'Agape (ἀγάπη) is the highest form of love—unconditional and steadfast. Trading crypto requires patience through extreme volatility and unwavering commitment to the system. Like love that always perseveres, this bot holds discipline through wild swings.',
  },
}

// =============================================================================
// ADVISOR SCRIPTURE REFERENCES
// =============================================================================

export const ADVISOR_SCRIPTURES: Record<string, BotScripture> = {
  ORACLE: {
    displayName: 'PROPHET',
    verse: '"Surely the Sovereign LORD does nothing without revealing his plan to his servants the prophets."',
    reference: 'Amos 3:7',
    why: 'The Oracle ML system forecasts market outcomes like a prophet reveals what is to come.',
  },
  SAGE: {
    displayName: 'WISDOM',
    verse: '"For the LORD gives wisdom; from his mouth come knowledge and understanding."',
    reference: 'Proverbs 2:6',
    why: 'SAGE provides ML-driven wisdom and probability predictions to guide trading decisions.',
  },
  ARGUS: {
    displayName: 'WATCHTOWER',
    verse: '"I have posted watchmen on your walls, Jerusalem; they will never be silent day or night."',
    reference: 'Isaiah 62:6 (see also Ezekiel 33:1-9)',
    why: 'ARGUS monitors 0DTE gamma in real-time like a watchman on the tower, alerting to danger.',
  },
  ORION: {
    displayName: 'STARS',
    verse: '"He determines the number of the stars and calls them each by name."',
    reference: 'Psalm 147:4',
    why: 'ORION uses GEX ML models for guidance, like stars guide travelers through the night.',
  },
  GEXIS: {
    displayName: 'COUNSELOR',
    verse: '"But the Advocate, the Holy Spirit, whom the Father will send in my name, will teach you all things."',
    reference: 'John 14:26',
    why: 'GEXIS is the AI assistant that counsels and guides through conversation.',
  },
  KRONOS: {
    displayName: 'CHRONICLES',
    verse: '"Remember the days of old; consider the generations long past."',
    reference: 'Deuteronomy 32:7',
    why: 'The backtester examines historical data, chronicling past performance to inform the future.',
  },
  HYPERION: {
    displayName: 'GLORY',
    verse: '"The heavens declare the glory of God; the skies proclaim the work of his hands."',
    reference: 'Psalm 19:1',
    why: 'HYPERION visualizes weekly gamma with clarity and beauty, revealing market structure.',
  },
  APOLLO: {
    displayName: 'DISCERNMENT',
    verse: '"And this is my prayer: that your love may abound more and more in knowledge and depth of insight, so that you may be able to discern what is best."',
    reference: 'Philippians 1:9-10',
    why: 'The ML Scanner discerns trading opportunities from noise, separating signal from static.',
  },
  SOLOMON: {
    displayName: 'PROVERBS',
    verse: '"The proverbs of Solomon son of David, king of Israel: for gaining wisdom and instruction; for understanding words of insight."',
    reference: 'Proverbs 1:1-2',
    why: 'The feedback loop distills trading outcomes into wisdom—proverbs for future decisions.',
  },
  NEXUS: {
    displayName: 'COVENANT',
    verse: '"I will make a covenant of peace with them; it will be an everlasting covenant."',
    reference: 'Ezekiel 37:26',
    why: 'NEXUS neural network forms connections between data points—a covenant linking all signals.',
  },
}

// =============================================================================
// SIMPLE NAME EXPORTS (for backward compatibility)
// =============================================================================

export const BOT_DISPLAY_NAMES = {
  ARES: BOT_SCRIPTURES.ARES.displayName,
  ATHENA: BOT_SCRIPTURES.ATHENA.displayName,
  ICARUS: BOT_SCRIPTURES.ICARUS.displayName,
  PEGASUS: BOT_SCRIPTURES.PEGASUS.displayName,
  TITAN: BOT_SCRIPTURES.TITAN.displayName,
  PHOENIX: BOT_SCRIPTURES.PHOENIX.displayName,
  ATLAS: BOT_SCRIPTURES.ATLAS.displayName,
  HERMES: BOT_SCRIPTURES.HERMES.displayName,
  PROMETHEUS: BOT_SCRIPTURES.PROMETHEUS.displayName,
  HERACLES: BOT_SCRIPTURES.HERACLES.displayName,
  AGAPE: BOT_SCRIPTURES.AGAPE.displayName,
} as const

export const ADVISOR_DISPLAY_NAMES = {
  ORACLE: ADVISOR_SCRIPTURES.ORACLE.displayName,
  SAGE: ADVISOR_SCRIPTURES.SAGE.displayName,
  ARGUS: ADVISOR_SCRIPTURES.ARGUS.displayName,
  ORION: ADVISOR_SCRIPTURES.ORION.displayName,
  GEXIS: ADVISOR_SCRIPTURES.GEXIS.displayName,
  KRONOS: ADVISOR_SCRIPTURES.KRONOS.displayName,
  HYPERION: ADVISOR_SCRIPTURES.HYPERION.displayName,
  APOLLO: ADVISOR_SCRIPTURES.APOLLO.displayName,
  SOLOMON: ADVISOR_SCRIPTURES.SOLOMON.displayName,
  NEXUS: ADVISOR_SCRIPTURES.NEXUS.displayName,
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
 */
export function getBotDisplayName(codename: string): string {
  const upperCodename = codename.toUpperCase() as BotCodename
  return BOT_DISPLAY_NAMES[upperCodename] || codename
}

/**
 * Get the display name for an advisory system
 */
export function getAdvisorDisplayName(codename: string): string {
  const upperCodename = codename.toUpperCase() as AdvisorCodename
  return ADVISOR_DISPLAY_NAMES[upperCodename] || codename
}

/**
 * Get full scripture info for a bot
 */
export function getBotScripture(codename: string): BotScripture | null {
  const upperCodename = codename.toUpperCase()
  return BOT_SCRIPTURES[upperCodename] || null
}

/**
 * Get full scripture info for an advisor
 */
export function getAdvisorScripture(codename: string): BotScripture | null {
  const upperCodename = codename.toUpperCase()
  return ADVISOR_SCRIPTURES[upperCodename] || null
}

/**
 * Get full display name with strategy description
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
