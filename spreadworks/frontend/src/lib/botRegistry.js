// Frontend mirror of spreadworks/backend/bots/registry.py.
// Keep these in sync when editing.

export const BOT_REGISTRY = {
  breeze: { display: 'BREEZE', strategy: 'iron_butterfly',  ticker: 'SPY', version: 'v1.4' },
  tide:   { display: 'TIDE',   strategy: 'double_calendar', ticker: 'SPY', version: 'v1.4' },
  drift:  { display: 'DRIFT',  strategy: 'double_diagonal', ticker: 'SPY', version: 'v1.4' },
  flow:   { display: 'FLOW',   strategy: 'iron_condor',     ticker: 'SPY', version: 'v1.0' },
};

export const STRATEGY_LABEL = {
  iron_butterfly:   'Iron Butterfly',
  double_calendar:  'Double Calendar',
  double_diagonal:  'Double Diagonal',
  iron_condor:      'Iron Condor',
};

// Per-bot theme palette mirrored from the SpreadWorks Design System
// (see design_handoff_bots/bots-data.jsx BOT_THEMES). The whole bot page
// tints to these colors — nameplate, equity curve, active tab, nav pill.
export const BOT_THEME = {
  breeze: {
    glyph:       'snowflake',
    primary:     '#22d3ee',                    // cyan-400
    primarySoft: 'rgba(34,211,238,0.10)',
    primaryRing: 'rgba(34,211,238,0.30)',
    glow:        'rgba(34,211,238,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(34,211,238,0.22) 0%, rgba(34,211,238,0.03) 100%)',
  },
  tide: {
    glyph:       'wave',
    primary:     '#2dd4bf',                    // teal-400
    primarySoft: 'rgba(45,212,191,0.10)',
    primaryRing: 'rgba(45,212,191,0.30)',
    glow:        'rgba(45,212,191,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(45,212,191,0.22) 0%, rgba(45,212,191,0.03) 100%)',
  },
  drift: {
    glyph:       'compass',
    primary:     '#a78bfa',                    // violet-400
    primarySoft: 'rgba(167,139,250,0.10)',
    primaryRing: 'rgba(167,139,250,0.30)',
    glow:        'rgba(167,139,250,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(167,139,250,0.22) 0%, rgba(167,139,250,0.03) 100%)',
  },
  flow: {
    glyph:       'river',                      // FLOW = current/river — distinct from breeze/tide/drift glyphs
    primary:     '#38bdf8',                    // sky-400
    primarySoft: 'rgba(56,189,248,0.10)',
    primaryRing: 'rgba(56,189,248,0.30)',
    glow:        'rgba(56,189,248,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(56,189,248,0.22) 0%, rgba(56,189,248,0.03) 100%)',
  },
};
