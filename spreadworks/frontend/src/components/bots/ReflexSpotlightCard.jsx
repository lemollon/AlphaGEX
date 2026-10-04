// REFLEX promotional card — visually in the same family as FleetPage's
// BotCard (sw-glass, hover lift, glyph chip) but NOT wired to useFleet() /
// useFleetStats(): there is no live P&L API for REFLEX, so this card never
// shows a live number. Every figure here is a labeled backtest result.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import BotGlyph from './BotGlyph';
import { BOT_THEME, STRATEGY_LABEL } from '../../lib/botRegistry';

const theme = BOT_THEME.reflex;
const MUTED = '#64748b';

function NewBadge() {
  return (
    <span
      className="flex items-center gap-1.5"
      style={{
        flexShrink: 0,
        fontSize: 9.5, fontWeight: 700, letterSpacing: '0.10em',
        textTransform: 'uppercase',
        padding: '3px 8px', borderRadius: 9999,
        color: theme.primary,
        background: theme.primarySoft,
        boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
      }}
    >
      <span style={{ width: 5, height: 5, borderRadius: 9999, background: theme.primary }} />
      New
    </span>
  );
}

function FreeBadge() {
  return (
    <span
      style={{
        flexShrink: 0,
        fontSize: 9.5, fontWeight: 700, letterSpacing: '0.10em',
        textTransform: 'uppercase',
        padding: '3px 8px', borderRadius: 9999,
        color: '#34d399',
        background: 'rgba(52,211,153,0.10)',
        boxShadow: 'inset 0 0 0 1px rgba(52,211,153,0.25)',
      }}
    >
      Free
    </span>
  );
}

function StatChip({ label, value }) {
  return (
    <div className="min-w-0">
      <div
        style={{
          fontSize: 9, fontWeight: 600, letterSpacing: '0.08em',
          textTransform: 'uppercase', color: MUTED,
        }}
      >
        {label}
      </div>
      <div
        className="truncate"
        style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700, marginTop: 2, color: theme.primary }}
      >
        {value}
      </div>
    </div>
  );
}

export default function ReflexSpotlightCard() {
  const [hover, setHover] = useState(false);

  return (
    <Link
      to="/reflex"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="sw-glass rounded-xl flex flex-col gap-3"
      style={{
        padding: 16,
        color: 'inherit',
        textDecoration: 'none',
        transition: 'transform 150ms, box-shadow 150ms',
        transform: hover ? 'translateY(-2px)' : 'none',
        boxShadow: hover
          ? `inset 0 0 0 1px ${theme.primaryRing}, 0 10px 30px -12px ${theme.glow}`
          : `inset 0 0 0 1px ${theme.primaryRing}`,
      }}
    >
      {/* header — glyph, name, strategy, badges */}
      <div className="flex items-center gap-3 min-w-0">
        <div
          style={{
            width: 34, height: 34, borderRadius: 8, flexShrink: 0,
            display: 'grid', placeItems: 'center',
            background: theme.primarySoft, color: theme.primary,
            boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
          }}
        >
          <BotGlyph kind={theme.glyph} size={16} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="truncate" style={{ fontSize: 15, fontWeight: 700, color: theme.primary }}>
            REFLEX
          </div>
          <div
            className="truncate"
            style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}
          >
            {STRATEGY_LABEL.reactive_momentum}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <NewBadge />
          <FreeBadge />
        </div>
      </div>

      {/* blurb */}
      <p className="text-[12.5px] text-text-secondary leading-relaxed">
        REFLEX waits until a stock is already up 10%+ with buying pressure accelerating — then gets in,
        holds to the close, and gets out. No guessing, no chasing hype early. Included free with your
        account.
      </p>

      {/* backtested stat chips */}
      <div>
        <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '0.10em', textTransform: 'uppercase', color: MUTED, marginBottom: 6 }}>
          Backtested — not live P&amp;L
        </div>
        <div
          className="grid grid-cols-3 gap-2"
          style={{ paddingTop: 10, borderTop: '1px solid rgba(125,211,252,0.08)' }}
        >
          <StatChip label="Trades" value="2,702" />
          <StatChip label="Symbols" value="605" />
          <StatChip label="Units (backtest)" value="+95.18" />
        </div>
      </div>
    </Link>
  );
}
