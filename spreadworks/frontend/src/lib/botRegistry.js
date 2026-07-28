// Frontend mirror of spreadworks/backend/bots/registry.py.
// Keep these in sync when editing.

export const BOT_REGISTRY = {
  surge: { display: 'SURGE', strategy: 'pin_drift_combo', ticker: 'SPY', version: 'v1.0' },
  splash: { display: 'SPLASH', strategy: 'long_butterfly', ticker: 'XSP', version: 'v2.1' },
  ripple: { display: 'RIPPLE', strategy: 'long_butterfly', ticker: 'SPX', version: 'v1.0' },
  tide:   { display: 'TIDE',   strategy: 'double_calendar', ticker: 'SPY', version: 'v1.4' },
  drift:  { display: 'DRIFT',  strategy: 'double_diagonal', ticker: 'SPY', version: 'v1.4' },
  flow:   { display: 'FLOW',   strategy: 'iron_condor',     ticker: 'SPY', version: 'v1.0' },
  meadow: { display: 'MEADOW', strategy: 'double_diagonal_credit', ticker: 'SPY', version: 'v1.0' },
  undertow: { display: 'UNDERTOW', strategy: 'vertical_debit', ticker: 'multi', version: 'v1.0' },
  delta: { display: 'DELTA', strategy: 'vertical_credit', ticker: 'multi', version: 'v1.0' },
  updraft: { display: 'UPDRAFT', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  backdraft: { display: 'BACKDRAFT', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  reversal: { display: 'REVERSAL', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  embreach: { display: 'EMBREACH', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  embreachq: { display: 'EMBREACHQ', strategy: 'updraft', ticker: 'QQQ', version: 'v1.0' },
  afterburn: { display: 'AFTERBURN', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  weekender: { display: 'WEEKENDER', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  flashpoint: { display: 'FLASHPOINT', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  thermal: { display: 'THERMAL', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
  wildfire: { display: 'WILDFIRE', strategy: 'updraft', ticker: 'SPY', version: 'v1.0' },
};

export const STRATEGY_LABEL = {
  // updraft-module MODES — position rows store the mode as their strategy,
  // so each card says which leg it belongs to.
  updraft:               'Flow-Fade Call (0DTE)',
  backdraft:             'Put-Wall Flow Call (0DTE)',
  reversal:              'RSI-Recovery Call (0DTE)',
  em_breach:             'EM-Breach Put (0DTE)',
  afterburn:             'Overnight Momentum Call (1DTE)',
  weekender:             'Weekend Hold Call (3DTE)',
  flashpoint:            'Wide-Range Breakout Call (0DTE)',
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

// Live A/B pairs: each bot's equity chart overlays its peer's curve. SPLASH
// (XSP, ~$200/lot) and RIPPLE (SPX, ~$2,000/lot) run the IDENTICAL validated
// fly strategy — the overlay compares vehicle + sizing on the same axes.
export const COMPARE_WITH = {
  splash: 'ripple',
  ripple: 'splash',
};

// Per-bot theme palette mirrored from the SpreadWorks Design System
// (see design_handoff_bots/bots-data.jsx BOT_THEMES). The whole bot page
// tints to these colors — nameplate, equity curve, active tab, nav pill.
export const BOT_THEME = {
  updraft: {
    glyph:       'wave',                       // UPDRAFT = put flow fading into a rising tape
    primary:     '#fbbf24',                    // amber-400
    primarySoft: 'rgba(251,191,36,0.10)',
    primaryRing: 'rgba(251,191,36,0.30)',
    glow:        'rgba(251,191,36,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(251,191,36,0.22) 0%, rgba(251,191,36,0.03) 100%)',
  },
  backdraft: {
    glyph:       'wave',                       // BACKDRAFT = the same fade, triggered by flow extremity
    primary:     '#fb7185',                    // rose-400
    primarySoft: 'rgba(251,113,133,0.10)',
    primaryRing: 'rgba(251,113,133,0.30)',
    glow:        'rgba(251,113,133,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(251,113,133,0.22) 0%, rgba(251,113,133,0.03) 100%)',
  },
  reversal: {
    glyph:       'wave',                       // REVERSAL = hourly RSI recovery cross
    primary:     '#34d399',                    // emerald-400
    primarySoft: 'rgba(52,211,153,0.10)',
    primaryRing: 'rgba(52,211,153,0.30)',
    glow:        'rgba(52,211,153,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(52,211,153,0.22) 0%, rgba(52,211,153,0.03) 100%)',
  },
  embreach: {
    glyph:       'wave',                       // EMBREACH = expected-move breach put
    primary:     '#a78bfa',                    // violet-400
    primarySoft: 'rgba(167,139,250,0.10)',
    primaryRing: 'rgba(167,139,250,0.30)',
    glow:        'rgba(167,139,250,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(167,139,250,0.22) 0%, rgba(167,139,250,0.03) 100%)',
  },
  embreachq: {
    glyph:       'wave',                       // EMBREACHQ = EMBREACH on QQQ
    primary:     '#c084fc',                    // purple-400 (violet sibling of EMBREACH)
    primarySoft: 'rgba(192,132,252,0.10)',
    primaryRing: 'rgba(192,132,252,0.30)',
    glow:        'rgba(192,132,252,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(192,132,252,0.22) 0%, rgba(192,132,252,0.03) 100%)',
  },
  afterburn: {
    glyph:       'wave',                       // AFTERBURN = strong close held overnight
    primary:     '#f97316',                    // orange-500
    primarySoft: 'rgba(249,115,22,0.10)',
    primaryRing: 'rgba(249,115,22,0.30)',
    glow:        'rgba(249,115,22,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(249,115,22,0.22) 0%, rgba(249,115,22,0.03) 100%)',
  },
  weekender: {
    glyph:       'wave',                       // WEEKENDER = Friday close held through the weekend
    primary:     '#38bdf8',                    // sky-400
    primarySoft: 'rgba(56,189,248,0.10)',
    primaryRing: 'rgba(56,189,248,0.30)',
    glow:        'rgba(56,189,248,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(56,189,248,0.22) 0%, rgba(56,189,248,0.03) 100%)',
  },
  wildfire: {
    glyph:       'wave',                       // WILDFIRE = backdraft that burns all day
    primary:     '#ef4444',                    // red-500
    primarySoft: 'rgba(239,68,68,0.10)',
    primaryRing: 'rgba(239,68,68,0.30)',
    glow:        'rgba(239,68,68,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(239,68,68,0.22) 0%, rgba(239,68,68,0.03) 100%)',
  },
  thermal: {
    glyph:       'wave',                       // THERMAL = the updraft you ride all day
    primary:     '#fb923c',                    // orange-400
    primarySoft: 'rgba(251,146,60,0.10)',
    primaryRing: 'rgba(251,146,60,0.30)',
    glow:        'rgba(251,146,60,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(251,146,60,0.22) 0%, rgba(251,146,60,0.03) 100%)',
  },
  flashpoint: {
    glyph:       'wave',                       // FLASHPOINT = wide-range morning ignites a breakout
    primary:     '#facc15',                    // yellow-400
    primarySoft: 'rgba(250,204,21,0.10)',
    primaryRing: 'rgba(250,204,21,0.30)',
    glow:        'rgba(250,204,21,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(250,204,21,0.22) 0%, rgba(250,204,21,0.03) 100%)',
  },
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
