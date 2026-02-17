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
  // FAITH (2DTE Paper IC - Trust, Confidence in the Unseen)
  // ─────────────────────────────────────────────────────────────────────────────
  FAITH: {
    displayName: 'FAITH',
    verse: '"Now faith is confidence in what we hope for and assurance about what we do not see."',
    reference: 'Hebrews 11:1',
    why: 'Paper trading requires faith—trusting the strategy with simulated capital before committing real money. Like faith that acts on conviction before seeing results, this bot proves the 2DTE Iron Condor thesis through disciplined paper execution.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // GRACE (1DTE Paper IC - Unmerited Favor, Comparison with FAITH)
  // ─────────────────────────────────────────────────────────────────────────────
  GRACE: {
    displayName: 'GRACE',
    verse: '"But by the grace of God I am what I am, and his grace to me was not without effect."',
    reference: '1 Corinthians 15:10',
    why: 'GRACE is the 1DTE companion to FAITH. Like grace that is given freely, this bot tests whether shorter-duration trades yield better results—comparing 1DTE to 2DTE Iron Condors side by side.',
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

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-SPOT → AGAPE-SPOT (24/7 Coinbase Spot - Unconditional Love, Extended)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_SPOT: {
    displayName: 'AGAPE-SPOT',
    verse: '"Love never fails. But where there are prophecies, they will cease; where there are tongues, they will be stilled; where there is knowledge, it will pass away."',
    reference: '1 Corinthians 13:8',
    why: 'AGAPE-SPOT extends the unconditional love of AGAPE to 24/7 spot trading across multiple coins. Like love that never fails and never ceases, this bot trades around the clock with unwavering patience through every market cycle.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-BTC → AGAPE-BTC (BTC Micro Futures - Unconditional Love, Bitcoin)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_BTC: {
    displayName: 'AGAPE-BTC',
    verse: '"And now these three remain: faith, hope and love. But the greatest of these is love."',
    reference: '1 Corinthians 13:13',
    why: 'AGAPE-BTC applies the same unconditional, disciplined love to Bitcoin futures. Like the greatest of virtues, it perseveres through volatility with steadfast devotion to the data-driven process.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-XRP → AGAPE-XRP (XRP Futures - Unconditional Love, XRP)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_XRP: {
    displayName: 'AGAPE-XRP',
    verse: '"Be completely humble and gentle; be patient, bearing with one another in love."',
    reference: 'Ephesians 4:2',
    why: 'AGAPE-XRP extends unconditional love to XRP futures trading. With humility and patience, it bears through each market cycle, finding opportunity where others see chaos.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-ETH-PERP → AGAPE-ETH-PERP (ETH Perpetual Contract)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_ETH_PERP: {
    displayName: 'AGAPE-ETH-PERP',
    verse: '"Love is patient, love is kind. It always protects, always trusts, always hopes, always perseveres."',
    reference: '1 Corinthians 13:4,7',
    why: 'AGAPE-ETH-PERP trades ETH perpetual contracts with the same steadfast discipline—24/7 commitment that never sleeps, like love that always perseveres.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-BTC-PERP → AGAPE-BTC-PERP (BTC Perpetual Contract)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_BTC_PERP: {
    displayName: 'AGAPE-BTC-PERP',
    verse: '"And now these three remain: faith, hope and love. But the greatest of these is love."',
    reference: '1 Corinthians 13:13',
    why: 'AGAPE-BTC-PERP applies unconditional devotion to Bitcoin perpetual contracts, trading around the clock with unwavering faith in the data-driven process.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-XRP-PERP → AGAPE-XRP-PERP (XRP Perpetual Contract)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_XRP_PERP: {
    displayName: 'AGAPE-XRP-PERP',
    verse: '"Be completely humble and gentle; be patient, bearing with one another in love."',
    reference: 'Ephesians 4:2',
    why: 'AGAPE-XRP-PERP trades XRP perpetual contracts with patience and humility through every market cycle, 24 hours a day.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-DOGE-PERP → AGAPE-DOGE-PERP (DOGE Perpetual Contract)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_DOGE_PERP: {
    displayName: 'AGAPE-DOGE-PERP',
    verse: '"Above all, love each other deeply, because love covers over a multitude of sins."',
    reference: '1 Peter 4:8',
    why: 'AGAPE-DOGE-PERP trades DOGE perpetual contracts—even meme coins deserve unconditional, disciplined love. Deep love covers the volatility of meme markets.',
  },

  // ─────────────────────────────────────────────────────────────────────────────
  // AGAPE-SHIB-PERP → AGAPE-SHIB-PERP (SHIB Perpetual Contract)
  // ─────────────────────────────────────────────────────────────────────────────
  AGAPE_SHIB_PERP: {
    displayName: 'AGAPE-SHIB-PERP',
    verse: '"Dear friends, let us love one another, for love comes from God."',
    reference: '1 John 4:7',
    why: 'AGAPE-SHIB-PERP trades SHIB perpetual contracts with divine patience. Even the smallest token receives the same unconditional love and disciplined approach.',
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
  PROVERBS: {
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
  // New biblical names (used in navigation and UI)
  FORTRESS: BOT_SCRIPTURES.ARES.displayName,
  FAITH: BOT_SCRIPTURES.FAITH.displayName,
  GRACE: BOT_SCRIPTURES.GRACE.displayName,
  SOLOMON: BOT_SCRIPTURES.ATHENA.displayName,
  GIDEON: BOT_SCRIPTURES.ICARUS.displayName,
  ANCHOR: BOT_SCRIPTURES.PEGASUS.displayName,
  SAMSON: BOT_SCRIPTURES.TITAN.displayName,
  LAZARUS: BOT_SCRIPTURES.PHOENIX.displayName,
  CORNERSTONE: BOT_SCRIPTURES.ATLAS.displayName,
  SHEPHERD: BOT_SCRIPTURES.HERMES.displayName,
  JUBILEE: BOT_SCRIPTURES.PROMETHEUS.displayName,
  VALOR: BOT_SCRIPTURES.HERACLES.displayName,
  AGAPE: BOT_SCRIPTURES.AGAPE.displayName,
  AGAPE_SPOT: BOT_SCRIPTURES.AGAPE_SPOT.displayName,
  AGAPE_BTC: BOT_SCRIPTURES.AGAPE_BTC.displayName,
  AGAPE_XRP: BOT_SCRIPTURES.AGAPE_XRP.displayName,
  AGAPE_ETH_PERP: BOT_SCRIPTURES.AGAPE_ETH_PERP.displayName,
  AGAPE_BTC_PERP: BOT_SCRIPTURES.AGAPE_BTC_PERP.displayName,
  AGAPE_XRP_PERP: BOT_SCRIPTURES.AGAPE_XRP_PERP.displayName,
  AGAPE_DOGE_PERP: BOT_SCRIPTURES.AGAPE_DOGE_PERP.displayName,
  AGAPE_SHIB_PERP: BOT_SCRIPTURES.AGAPE_SHIB_PERP.displayName,
} as const

export const ADVISOR_DISPLAY_NAMES = {
  // New biblical names (used in navigation and UI)
  PROPHET: ADVISOR_SCRIPTURES.ORACLE.displayName,
  WISDOM: ADVISOR_SCRIPTURES.SAGE.displayName,
  WATCHTOWER: ADVISOR_SCRIPTURES.ARGUS.displayName,
  STARS: ADVISOR_SCRIPTURES.ORION.displayName,
  COUNSELOR: ADVISOR_SCRIPTURES.GEXIS.displayName,
  CHRONICLES: ADVISOR_SCRIPTURES.KRONOS.displayName,
  GLORY: ADVISOR_SCRIPTURES.HYPERION.displayName,
  DISCERNMENT: ADVISOR_SCRIPTURES.APOLLO.displayName,
  PROVERBS: ADVISOR_SCRIPTURES.PROVERBS.displayName,
  COVENANT: ADVISOR_SCRIPTURES.NEXUS.displayName,
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
