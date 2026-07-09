// Frontend mirror of spreadworks/backend/bots/registry.py.
// Keep these in sync when editing.

export const BOT_REGISTRY = {
  surge: { display: 'SURGE', strategy: 'pin_drift_combo', ticker: 'SPY', version: 'v1.0' },
  splash: { display: 'SPLASH', strategy: 'long_butterfly', ticker: 'SPX', version: 'v2.0' },
  ripple: { display: 'RIPPLE', strategy: 'long_butterfly', ticker: 'SPX', version: 'v1.0' },
  tide:   { display: 'TIDE',   strategy: 'double_calendar', ticker: 'SPY', version: 'v1.4' },
  drift:  { display: 'DRIFT',  strategy: 'double_diagonal', ticker: 'SPY', version: 'v1.4' },
  flow:   { display: 'FLOW',   strategy: 'iron_condor',     ticker: 'SPY', version: 'v1.0' },
  meadow: { display: 'MEADOW', strategy: 'double_diagonal_credit', ticker: 'SPY', version: 'v1.0' },
  undertow: { display: 'UNDERTOW', strategy: 'vertical_debit', ticker: 'multi', version: 'v1.0' },
  delta: { display: 'DELTA', strategy: 'vertical_credit', ticker: 'multi', version: 'v1.0' },
};

export const STRATEGY_LABEL = {
  iron_butterfly:        'Iron Butterfly',
  pin_drift_combo:       'Pin + Drift Combo',
  double_calendar:       'Double Calendar',
  double_diagonal:       'Double Diagonal',
  iron_condor:           'Iron Condor',
  double_diagonal_credit: 'Credit Double Diagonal',
  long_butterfly:        'Long Butterfly',
  dip_buy:               'Dip-Buy Call',
  vertical_debit:        'Debit Vertical',
  vertical_credit:       'Credit Vertical',
};

// Live A/B pairs: each bot's equity chart overlays its peer's curve so the
// two configs (SPLASH wing 1.0 + 14:45 buyback vs RIPPLE wing 1.5 + cash
// settlement) can be compared on the same axes.
export const COMPARE_WITH = {
  splash: 'ripple',
  ripple: 'splash',
};

// Per-bot theme palette mirrored from the SpreadWorks Design System
// (see design_handoff_bots/bots-data.jsx BOT_THEMES). The whole bot page
// tints to these colors — nameplate, equity curve, active tab, nav pill.
export const BOT_THEME = {
  surge: {
    glyph:       'wave',                        // SURGE = where the pin + drift structures meet
    primary:     '#22d3ee',                    // cyan-400
    primarySoft: 'rgba(34,211,238,0.10)',
    primaryRing: 'rgba(34,211,238,0.30)',
    glow:        'rgba(34,211,238,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(34,211,238,0.22) 0%, rgba(34,211,238,0.03) 100%)',
  },
  splash: {
    glyph:       'droplet',                    // SPLASH = 0DTE long butterfly (fly-only, v2)
    primary:     '#60a5fa',                    // blue-400
    primarySoft: 'rgba(96,165,250,0.10)',
    primaryRing: 'rgba(96,165,250,0.30)',
    glow:        'rgba(96,165,250,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(96,165,250,0.22) 0%, rgba(96,165,250,0.03) 100%)',
  },
  ripple: {
    glyph:       'wave',                       // RIPPLE = rings spreading out — SPLASH's settle-at-expiry A/B twin
    primary:     '#f0abfc',                    // fuchsia-300
    primarySoft: 'rgba(240,171,252,0.10)',
    primaryRing: 'rgba(240,171,252,0.30)',
    glow:        'rgba(240,171,252,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(240,171,252,0.22) 0%, rgba(240,171,252,0.03) 100%)',
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
  meadow: {
    glyph:       'sprout',                      // MEADOW = a seedling/sprout — grassy, distinct from the others
    primary:     '#34d399',                    // emerald-400
    primarySoft: 'rgba(52,211,153,0.10)',
    primaryRing: 'rgba(52,211,153,0.30)',
    glow:        'rgba(52,211,153,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(52,211,153,0.22) 0%, rgba(52,211,153,0.03) 100%)',
  },
  undertow: {
    glyph:       'wave',                       // UNDERTOW = a pulling undercurrent
    primary:     '#818cf8',                    // indigo-400
    primarySoft: 'rgba(129,140,248,0.10)',
    primaryRing: 'rgba(129,140,248,0.30)',
    glow:        'rgba(129,140,248,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(129,140,248,0.22) 0%, rgba(129,140,248,0.03) 100%)',
  },
  delta: {
    glyph:       'wave',
    primary:     '#14b8a6',                    // teal-500
    primarySoft: 'rgba(20,184,166,0.10)',
    primaryRing: 'rgba(20,184,166,0.30)',
    glow:        'rgba(20,184,166,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(20,184,166,0.22) 0%, rgba(20,184,166,0.03) 100%)',
  },
};
