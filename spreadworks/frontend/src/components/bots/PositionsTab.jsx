import { useState } from 'react';
import { Inbox } from 'lucide-react';
import { useBotPositions } from '../../hooks/useBotPositions';
import { botApi } from '../../lib/botApi';
import { BOT_THEME, BOT_REGISTRY, STRATEGY_LABEL } from '../../lib/botRegistry';
import BotGlyph from './BotGlyph';
import BotPayoffChart from './BotPayoffChart';
import AdjustPositionModal from './AdjustPositionModal';

/* ─── Helpers ──────────────────────────────────────────────────── */

function formatOpened(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    return d.toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }) + ' CT';
  } catch {
    return String(ts);
  }
}

function relativeTime(ts) {
  if (!ts) return 'just now';
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 0) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function computeDte(legs) {
  if (!Array.isArray(legs) || legs.length === 0) return null;
  // Front expiration is the earliest leg expiration.
  const exps = legs.map(l => l.expiration).filter(Boolean).sort();
  if (exps.length === 0) return null;
  try {
    const exp = new Date(exps[0] + 'T00:00:00');
    const today = new Date();
    const ms = exp.setHours(0, 0, 0, 0) - today.setHours(0, 0, 0, 0);
    return Math.max(0, Math.round(ms / 86400000));
  } catch {
    return null;
  }
}

// Pluck the four canonical legs (longPut / shortPut / shortCall / longCall)
// from a raw legs array. Some strategies (iron_butterfly) reuse the same
// strike for shortPut + shortCall — that's preserved, just shown twice.
function pluckLegs(legs) {
  const out = { longPut: null, shortPut: null, shortCall: null, longCall: null };
  for (const l of legs || []) {
    if (l.side === 'long' && l.type === 'put')  out.longPut   = Number(l.strike);
    if (l.side === 'short' && l.type === 'put') out.shortPut  = Number(l.strike);
    if (l.side === 'short' && l.type === 'call') out.shortCall = Number(l.strike);
    if (l.side === 'long' && l.type === 'call')  out.longCall  = Number(l.strike);
  }
  return out;
}

/* ─── PositionCard (per spec) ──────────────────────────────────── */

function PositionCard({ p, bot, theme, isChartOpen, onToggleChart, onForceClose, onAdjust }) {
  const legsRaw = typeof p.legs === 'string'
    ? (() => { try { return JSON.parse(p.legs); } catch { return []; } })()
    : (p.legs || []);
  const legs = pluckLegs(legsRaw);
  const symbol = p.ticker || 'SPY';
  const strategy = STRATEGY_LABEL[p.strategy] || p.strategy;
  const qty = Number(p.contracts) || 1;
  const dte = computeDte(legsRaw);

  const pnl = p.mtm_pnl != null ? Number(p.mtm_pnl) : 0;
  const positive = pnl >= 0;
  const pnlColor = positive ? '#34d399' : '#fb7185';
  const entryCredit = Number(p.entry_price) || 0;
  const current = p.mtm_value != null ? Number(p.mtm_value) : 0;
  const pnlPct = entryCredit && qty
    ? pnl / (Math.abs(entryCredit) * qty * 100)
    : 0;

  const pt = Math.abs(Number(p.pt_target_pnl) || 0);
  const sl = Math.abs(Number(p.sl_target_pnl) || 0);

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'stretch',
        borderRadius: 12,
        overflow: 'hidden',
        background: 'rgba(13,28,46,0.55)',
        backdropFilter: 'blur(12px) saturate(140%)',
        WebkitBackdropFilter: 'blur(12px) saturate(140%)',
        boxShadow:
          'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)',
      }}
    >
      {/* ───────────── LEFT ACCENT STRIPE ───────────── */}
      <div
        style={{
          width: 6,
          flexShrink: 0,
          background: `linear-gradient(180deg, ${theme.primary}, ${theme.primary}33)`,
        }}
      />

      {/* ───────────── BODY ───────────── */}
      <div style={{ flex: 1, padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* HEADER ROW */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {/* Bot glyph tile */}
            <div
              style={{
                width: 44, height: 44, borderRadius: 8,
                display: 'grid', placeItems: 'center',
                background: theme.primarySoft,
                boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
                color: theme.primary,
              }}
            >
              <BotGlyph kind={theme.glyph} size={20} strokeWidth={1.6} />
            </div>

            {/* Identity */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'JetBrains Mono', fontSize: 15, fontWeight: 700, color: '#fff' }}>
                  {symbol}
                </span>
                <span style={{ fontSize: 13, color: '#cbd5e1', fontWeight: 500 }}>
                  {strategy}
                </span>
                <span
                  style={{
                    fontFamily: 'JetBrains Mono',
                    fontSize: 10.5,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    fontWeight: 700,
                    padding: '2px 8px',
                    borderRadius: 4,
                    color: '#67e8f9',
                    background: 'rgba(34,211,238,0.10)',
                    boxShadow: 'inset 0 0 0 1px rgba(34,211,238,0.30)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {qty}× · DTE {dte ?? '—'}
                </span>
              </div>
              <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10.5, color: '#64748b', marginTop: 4 }}>
                Opened {formatOpened(p.entry_time)}
              </div>
            </div>
          </div>

          {/* HERO P&L */}
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <Label>Unrealized</Label>
            <div
              style={{
                fontFamily: 'JetBrains Mono',
                fontSize: 32,
                fontWeight: 900,
                lineHeight: 1,
                marginTop: 6,
                color: pnlColor,
                textShadow: `0 0 18px ${pnlColor}55`,
              }}
            >
              {positive ? '+' : '−'}${Math.abs(pnl).toFixed(2)}
            </div>
            <div
              style={{
                fontFamily: 'JetBrains Mono',
                fontSize: 11,
                fontWeight: 600,
                marginTop: 6,
                color: pnlColor,
                opacity: 0.85,
              }}
            >
              {positive ? '+' : '−'}{Math.abs(pnlPct * 100).toFixed(1)}% on credit
            </div>
          </div>
        </div>

        {/* LEG CHIPS */}
        <LegChips legs={legs} />

        {/* PT/SL PROGRESS BAR */}
        <PtSlBar pnl={pnl} pt={pt} sl={sl} />

        {/* STATS + ACTIONS ROW */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 4, gap: 12, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 20, fontFamily: 'JetBrains Mono', fontSize: 12 }}>
            <InlineStat label="Entry"   value={`$${entryCredit.toFixed(2)}`} />
            <InlineStat label="Current" value={`$${current.toFixed(2)}`} />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <GhostBtn onClick={onAdjust} title="Adjust PT / SL targets">Adjust</GhostBtn>
            <GhostBtn disabled title="Coming soon">Roll</GhostBtn>
            <ThemedBtn theme={theme} onClick={onToggleChart}>
              {isChartOpen ? 'Hide Chart' : 'Chart'}
            </ThemedBtn>
            <DangerBtn onClick={onForceClose}>Close</DangerBtn>
          </div>
        </div>

        {/* Optional payoff chart drawer */}
        {isChartOpen && (
          <div
            style={{
              marginTop: 4,
              paddingTop: 12,
              borderTop: '1px solid rgba(125,211,252,0.08)',
            }}
          >
            <BotPayoffChart
              bot={bot}
              positionId={p.position_id}
              contracts={qty}
              height={210}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── PT/SL Progress Bar ───────────────────────────────────────── */

function PtSlBar({ pnl, pt, sl }) {
  const range = pt + sl;
  // Defend against zero/missing config so the bar still renders the markers
  // (a degenerate range collapses to a centered $0 with no dot motion).
  const safeRange = range > 0 ? range : 1;
  const centerPct = (sl / safeRange) * 100;
  const rawDotPct = ((sl + pnl) / safeRange) * 100;
  const dotPct = Math.max(0, Math.min(100, rawDotPct));
  return (
    <div>
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          fontSize: 9, fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.12em', marginBottom: 6,
        }}
      >
        <span style={{ color: '#fb7185' }}>SL −${Math.round(sl)}</span>
        <span style={{ color: '#64748b' }}>$0</span>
        <span style={{ color: '#34d399' }}>PT +${Math.round(pt)}</span>
      </div>
      <div
        style={{
          position: 'relative',
          height: 6,
          borderRadius: 9999,
          background: 'rgba(125,211,252,0.08)',
        }}
      >
        {/* $0 tick */}
        <div
          style={{
            position: 'absolute', top: 0, bottom: 0,
            left: `${centerPct}%`, width: 1,
            background: 'rgba(125,211,252,0.30)',
          }}
        />
        {/* current-P&L dot — amber to match Now markers elsewhere */}
        <div
          style={{
            position: 'absolute',
            top: -4,
            left: `calc(${dotPct}% - 7px)`,
            width: 14, height: 14, borderRadius: 9999,
            background: '#fcd34d',
            boxShadow: '0 0 10px rgba(252,211,77,0.7), inset 0 0 0 2px #06121f',
          }}
        />
      </div>
    </div>
  );
}

/* ─── Leg chips ─────────────────────────────────────────────────── */

function LegChips({ legs }) {
  const items = [
    { side: 'long',  type: 'P', strike: legs.longPut },
    { side: 'short', type: 'P', strike: legs.shortPut },
    { side: 'short', type: 'C', strike: legs.shortCall },
    { side: 'long',  type: 'C', strike: legs.longCall },
  ];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      {items.map((l, i) => {
        if (l.strike == null) return null;
        const isLong = l.side === 'long';
        const color = isLong ? '#34d399' : '#fb7185';
        const bg    = isLong ? 'rgba(52,211,153,0.10)' : 'rgba(251,113,133,0.10)';
        const ring  = isLong ? 'rgba(52,211,153,0.25)' : 'rgba(251,113,133,0.25)';
        return (
          <span
            key={i}
            style={{
              fontFamily: 'JetBrains Mono',
              fontSize: 11.5,
              fontWeight: 600,
              padding: '4px 10px',
              borderRadius: 6,
              background: bg,
              color: color,
              boxShadow: `inset 0 0 0 1px ${ring}`,
            }}
          >
            {isLong ? '+' : '−'}${l.strike}{l.type}
          </span>
        );
      })}
    </div>
  );
}

/* ─── Inline helpers ───────────────────────────────────────────── */

function Label({ children }) {
  return (
    <span style={{
      fontSize: 9.5,
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.14em',
      color: '#64748b',
    }}>
      {children}
    </span>
  );
}

function InlineStat({ label, value }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6 }}>
      <Label>{label}</Label>
      <span style={{ fontSize: 12.5, fontWeight: 700, color: '#fff' }}>{value}</span>
    </span>
  );
}

function GhostBtn({ children, onClick, disabled, title }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
        color: '#cbd5e1', background: 'rgba(7,16,28,0.55)',
        boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10)',
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
      }}
    >
      {children}
    </button>
  );
}

function ThemedBtn({ theme, children, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
        color: theme.primary, background: theme.primarySoft,
        boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
        border: 'none', cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}

function DangerBtn({ children, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
        color: '#fb7185', background: 'rgba(251,113,133,0.10)',
        boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.30)',
        border: 'none', cursor: 'pointer',
      }}
    >
      {children}
    </button>
  );
}

/* ─── Tab container ────────────────────────────────────────────── */

export default function PositionsTab({ bot, lastScanAt, enabled = true }) {
  const { positions } = useBotPositions(bot, 5000);
  const theme = BOT_THEME[bot];
  const meta = BOT_REGISTRY[bot];
  const [openCharts, setOpenCharts] = useState(() => new Set());
  const [adjusting, setAdjusting] = useState(null); // position object or null

  function toggleChart(pid) {
    setOpenCharts(prev => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid); else next.add(pid);
      return next;
    });
  }

  async function onClose(pid) {
    if (!confirm('Force-close this position?')) return;
    await botApi.forceClose(bot, pid);
  }

  if (positions.length === 0) {
    const scanLabel = enabled
      ? `Scanning · ${relativeTime(lastScanAt)}`
      : 'Scanner paused';
    const dotClass = enabled ? 'bg-sw-green animate-pulse' : 'bg-text-tertiary';
    return (
      <div className="px-5 py-16 flex flex-col items-center text-center">
        <div
          className="w-14 h-14 rounded-full grid place-items-center mb-4"
          style={{
            background: theme.primarySoft,
            boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
          }}
        >
          <Inbox size={22} style={{ color: theme.primary }} strokeWidth={1.5} />
        </div>
        <div className="text-[14px] font-semibold text-white mb-1">No open positions</div>
        <div className="text-[12.5px] text-text-tertiary max-w-sm leading-relaxed">
          {meta?.display || bot.toUpperCase()} is scanning for a setup. The next
          trade will appear here automatically when filters match.
        </div>
        <div className="flex items-center gap-2 mt-5 text-[11px] text-text-tertiary">
          <span className="inline-flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
            {scanLabel}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 py-5 space-y-3">
      {positions.map(p => (
        <PositionCard
          key={p.position_id}
          p={p}
          bot={bot}
          theme={theme}
          isChartOpen={openCharts.has(p.position_id)}
          onToggleChart={() => toggleChart(p.position_id)}
          onForceClose={() => onClose(p.position_id)}
          onAdjust={() => setAdjusting(p)}
        />
      ))}
      {adjusting && (
        <AdjustPositionModal
          bot={bot}
          position={adjusting}
          theme={theme}
          onClose={() => setAdjusting(null)}
          onSaved={() => { /* hook auto-refreshes every 5s */ }}
        />
      )}
    </div>
  );
}
