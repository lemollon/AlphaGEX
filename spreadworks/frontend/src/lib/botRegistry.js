// Frontend mirror of spreadworks/backend/bots/registry.py.
// Keep these in sync when editing.

export const BOT_REGISTRY = {
  breeze: { display: 'BREEZE', strategy: 'iron_butterfly',  ticker: 'SPY' },
  tide:   { display: 'TIDE',   strategy: 'double_calendar', ticker: 'SPY' },
  drift:  { display: 'DRIFT',  strategy: 'double_diagonal', ticker: 'SPY' },
};

export const STRATEGY_LABEL = {
  iron_butterfly:   'Iron Butterfly',
  double_calendar:  'Double Calendar',
  double_diagonal:  'Double Diagonal',
};

export const BOT_THEME = {
  breeze: { accent: '#A5F3FC', glyph: 'snowflake' },
  tide:   { accent: '#38BDF8', glyph: 'wave' },
  drift:  { accent: '#7DD3FC', glyph: 'current' },
};
