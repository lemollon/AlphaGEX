// REFLEX promotional card — restyled 2026-10-05 to match FleetPage's BotCard
// shape/fields/typography exactly (header row, headline block, 3-col footer,
// bottom footer), not just its glass/hover-lift family. Still NOT wired to
// useFleet() / useFleetStats(): there is no live P&L API for REFLEX, so every
// number here is a labeled backtest result, never presented as live P&L.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import BotGlyph from './BotGlyph';
import { BOT_THEME, STRATEGY_LABEL } from '../../lib/botRegistry';

const theme = BOT_THEME.reflex;
const GREEN = '#34d399';
const MUTED = '#64748b';

const LABEL_STYLE = {
  fontSize: 9, fontWeight: 600, letterSpacing: '0.08em',
  textTransform: 'uppercase', color: MUTED,
};

// Same slot BotCard uses for its Live/Paused pill — REFLEX isn't "live" in
// that sense (zero trades, waiting on a $500 capital floor), so it reads
// "New" instead of asserting a status this card cannot back up.
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

// Same slot BotCard uses for its AccountChip (PAPER / LIVE $) — REFLEX has no
// account to label, so the chip carries the other fact that matters here.
function FreeBadge() {
  return (
    <span
      style={{
        flexShrink: 0,
        fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
        textTransform: 'uppercase', padding: '2px 7px', borderRadius: 9999,
        color: '#34d399',
        background: 'transparent',
        boxShadow: 'inset 0 0 0 1px rgba(52,211,153,0.35)',
      }}
    >
      Free
    </span>
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
          : 'inset 0 0 0 1px rgba(125,211,252,0.08)',
      }}
    >
      {/* header — glyph, name, strategy, status pills (same shape as BotCard) */}
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
            Reflex
          </div>
          <div
            className="truncate"
            style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}
          >
            {STRATEGY_LABEL.reactive_momentum}
          </div>
          <div style={{ marginTop: 4 }}>
            <span style={{
              fontFamily: 'JetBrains Mono', fontSize: 10, fontWeight: 700,
              padding: '2px 6px', borderRadius: 5, letterSpacing: 0.3,
              background: 'rgba(125,211,252,0.06)',
              color: MUTED,
              boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10)',
            }}
            title="Scans the full market — not a single-ticker bot">
              multi
            </span>
          </div>
        </div>

        <NewBadge />
        <FreeBadge />
      </div>

      {/* headline — same slot as BotCard's "Today" P&L, relabeled since
          REFLEX has no live P&L yet */}
      <div>
        <div style={{ ...LABEL_STYLE, fontSize: 9.5, letterSpacing: '0.10em' }}>
          Backtest avg/trade
        </div>
        <div
          style={{
            fontFamily: 'JetBrains Mono', fontSize: 26, fontWeight: 700,
            lineHeight: 1.15, marginTop: 2, color: GREEN,
          }}
        >
          +3.52%
        </div>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}>
          2,702 trades · 605 symbols · 3.5y backtest
        </div>
      </div>

      {/* 3-col footer — same shape as BotCard's Total / Equity / Open */}
      <div
        className="grid grid-cols-3 gap-2"
        style={{ paddingTop: 12, borderTop: '1px solid rgba(125,211,252,0.08)' }}
      >
        <div className="min-w-0">
          <div style={LABEL_STYLE}>Total (bt)</div>
          <div
            className="truncate"
            style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700, marginTop: 2, color: GREEN }}
          >
            +95.18u
          </div>
        </div>
        <div className="min-w-0">
          <div style={LABEL_STYLE}>Robust</div>
          <div
            className="truncate"
            style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700, marginTop: 2, color: GREEN }}
            title="Still profitable with the single best trade removed"
          >
            +75.13u
          </div>
        </div>
        <div className="min-w-0">
          <div style={LABEL_STYLE}>Symbols</div>
          <div
            style={{ fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700, marginTop: 2, color: theme.primary }}
          >
            605
          </div>
        </div>
      </div>

      <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED }}>
        Backtested — not live P&amp;L
      </div>

      {/* footer — same shape as BotCard's version / scanned-time row */}
      <div
        className="flex items-center justify-between gap-2"
        style={{
          marginTop: 'auto', paddingTop: 8,
          borderTop: '1px solid rgba(125,211,252,0.06)',
          fontFamily: 'JetBrains Mono', fontSize: 9.5, color: MUTED,
        }}
      >
        <span className="truncate">v1.0</span>
        <span className="truncate" style={{ flexShrink: 0 }}>
          zero live trades yet
        </span>
      </div>
    </Link>
  );
}
