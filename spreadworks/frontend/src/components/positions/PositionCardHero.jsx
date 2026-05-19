import { useState, useEffect } from 'react';
import { STRAT_LABELS } from '../../lib/strategies';
import { API_URL } from '../../lib/api';

/* ─── Helpers ──────────────────────────────────────────────────── */

function formatOpened(raw) {
  if (!raw) return '—';
  try {
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return String(raw);
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
    return String(raw);
  }
}

/* ─── Card ─────────────────────────────────────────────────────── */

export default function PositionCardHero({ position, onClose, onAdjust }) {
  const [pnl, setPnl] = useState(null);

  useEffect(() => {
    if (position.status !== 'open') return;
    let cancelled = false;
    const fetchPnl = async () => {
      try {
        const res = await fetch(`${API_URL}/api/spreadworks/positions/${position.id}/pnl`);
        if (res.ok && !cancelled) setPnl(await res.json());
      } catch { /* silent */ }
    };
    fetchPnl();
    const iv = setInterval(fetchPnl, 60000);
    return () => { cancelled = true; clearInterval(iv); };
  }, [position.id, position.status]);

  const unrealized   = pnl?.unrealized_pnl ?? 0;
  const currentValue = pnl?.current_value ?? 0;
  // /pnl returns pnl_pct as a percentage number (e.g. 2.8 == 2.8%). Convert
  // to decimal so the Dial helper can multiply by 100 itself.
  const pnlPctDecimal = (pnl?.pnl_pct ?? 0) / 100;

  const symbol        = position.symbol || 'SPY';
  const strategy      = STRAT_LABELS[position.strategy] || position.strategy;
  const qty           = Number(position.contracts) || 1;
  const dte           = position.dte ?? null;
  const entryCredit   = Math.abs(Number(position.entry_credit) || 0);
  const ptDollar      = Math.abs(Number(position.max_profit) || 0);
  const slDollar      = Math.abs(Number(position.max_loss)   || 0);

  const positive = unrealized >= 0;
  const pnlColor = positive ? '#34d399' : '#fb7185';

  return (
    <div
      style={{
        position: 'relative',
        borderRadius: 16,
        overflow: 'hidden',
        background: 'linear-gradient(135deg, rgba(167,139,250,0.18), rgba(52,211,153,0.10) 100%)',
        boxShadow: '0 0 60px -20px rgba(167,139,250,0.4), inset 0 0 0 1px rgba(125,211,252,0.15)',
      }}
    >
      {/* soft top-right radial overlay */}
      <div
        style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'radial-gradient(80% 60% at 80% 0%, rgba(52,211,153,0.18), transparent 60%)',
        }}
      />

      <div
        style={{
          position: 'relative',
          padding: 28,
          display: 'grid',
          gridTemplateColumns: '1.4fr auto',
          gap: 28,
          alignItems: 'center',
        }}
      >
        {/* ───────── LEFT — identity / legs / stats / actions ───────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
          {/* Identity */}
          <div>
            <div style={{
              fontSize: 10, fontWeight: 700,
              textTransform: 'uppercase', letterSpacing: '0.24em',
              color: '#c4b5fd',
            }}>
              {strategy}
            </div>
            <div style={{
              fontFamily: 'JetBrains Mono',
              fontSize: 44, fontWeight: 900,
              color: '#fff', marginTop: 4,
              lineHeight: 1, letterSpacing: '-0.02em',
            }}>
              {symbol}
            </div>
            <div style={{
              fontFamily: 'JetBrains Mono',
              fontSize: 10.5, color: '#94a3b8', marginTop: 8,
            }}>
              Opened {formatOpened(position.entry_date)} · {qty}× · DTE {dte ?? '—'}
            </div>
          </div>

          {/* Leg chips */}
          <LegChips
            longPut={position.long_put}
            shortPut={position.short_put}
            shortCall={position.short_call}
            longCall={position.long_call}
          />

          {/* Stats grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: 16,
              paddingTop: 12,
              borderTop: '1px solid rgba(125,211,252,0.10)',
            }}
          >
            <Stat label="Entry"        value={`$${entryCredit.toFixed(2)}`} color="#fff" />
            <Stat label="Current"      value={`$${currentValue.toFixed(2)}`} color="#fff" />
            <Stat label="Profit take"  value={`+$${Math.round(ptDollar)}`}   color="#34d399" />
            <Stat label="Stop loss"    value={`−$${Math.round(slDollar)}`}   color="#fb7185" />
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8 }}>
            <GhostBtn onClick={onAdjust} disabled={!onAdjust} title={onAdjust ? 'Adjust PT / SL targets' : 'Coming soon'}>
              Adjust
            </GhostBtn>
            <GhostBtn disabled title="Coming soon">Roll</GhostBtn>
            <button
              onClick={() => onClose?.(position)}
              style={{
                marginLeft: 'auto',
                padding: '8px 16px', borderRadius: 8,
                fontSize: 13, fontWeight: 700, color: '#fff',
                background: 'rgba(251,113,133,0.30)',
                boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.50)',
                border: 'none', cursor: 'pointer',
              }}
            >
              Close position
            </button>
          </div>
        </div>

        {/* ───────── RIGHT — gauge dial ───────── */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <Dial
            pct={ptDollar > 0 ? unrealized / ptDollar : 0}
            pnl={unrealized}
            pctOnCredit={pnlPctDecimal}
            color={pnlColor}
          />
          <div style={{
            display: 'flex', alignItems: 'center', gap: 16,
            fontFamily: 'JetBrains Mono', fontSize: 10.5,
          }}>
            <span style={{ color: '#fb7185' }}>SL −${Math.round(slDollar)}</span>
            <span style={{ color: '#64748b' }}>·</span>
            <span style={{ color: '#34d399' }}>PT +${Math.round(ptDollar)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Circular gauge dial ──────────────────────────────────────── */

function Dial({ pct, pnl, pctOnCredit, color }) {
  const safe = Math.max(0, Math.min(1, Number.isFinite(pct) ? pct : 0));
  const R = 64;
  const C = 2 * Math.PI * R;
  const positive = pnl >= 0;

  return (
    <div style={{ position: 'relative', width: 180, height: 180, display: 'grid', placeItems: 'center' }}>
      <svg
        viewBox="0 0 160 160"
        style={{ position: 'absolute', inset: 0, transform: 'rotate(-90deg)' }}
      >
        {/* track */}
        <circle cx="80" cy="80" r={R} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
        {/* progress */}
        <circle
          cx="80" cy="80" r={R} fill="none"
          stroke={color} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={C * (1 - safe)}
          style={{ filter: `drop-shadow(0 0 10px ${color}b3)`, transition: 'stroke-dashoffset 400ms ease-out' }}
        />
      </svg>
      <div style={{ position: 'relative', textAlign: 'center' }}>
        <div style={{
          fontSize: 9, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '0.20em',
          color: `${color}b3`, marginBottom: 4,
        }}>
          UNREALIZED
        </div>
        <div style={{
          fontFamily: 'JetBrains Mono',
          fontSize: 32, fontWeight: 900,
          color, lineHeight: 1,
          textShadow: `0 0 18px ${color}99`,
        }}>
          {positive ? '+' : '−'}${Math.abs(pnl).toFixed(2)}
        </div>
        <div style={{
          fontFamily: 'JetBrains Mono',
          fontSize: 11, fontWeight: 700,
          color: `${color}cc`, marginTop: 8,
        }}>
          {positive ? '+' : '−'}{Math.abs(pctOnCredit * 100).toFixed(1)}% · {(safe * 100).toFixed(0)}% to PT
        </div>
      </div>
    </div>
  );
}

/* ─── Leg chips ────────────────────────────────────────────────── */

function LegChips({ longPut, shortPut, shortCall, longCall }) {
  const items = [
    { side: 'long',  type: 'P', strike: longPut   },
    { side: 'short', type: 'P', strike: shortPut  },
    { side: 'short', type: 'C', strike: shortCall },
    { side: 'long',  type: 'C', strike: longCall  },
  ];
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      {items.map((l, i) => {
        if (l.strike == null) return null;
        const isLong = l.side === 'long';
        const color = isLong ? '#34d399' : '#fb7185';
        const bg    = isLong ? 'rgba(52,211,153,0.10)' : 'rgba(251,113,133,0.10)';
        return (
          <span
            key={i}
            style={{
              fontFamily: 'JetBrains Mono',
              fontSize: 11.5, fontWeight: 600,
              padding: '4px 10px', borderRadius: 6,
              background: bg, color,
              boxShadow: `inset 0 0 0 1px ${color}40`,
            }}
          >
            {isLong ? '+' : '−'}${l.strike}{l.type}
          </span>
        );
      })}
    </div>
  );
}

/* ─── Small helpers ────────────────────────────────────────────── */

function Stat({ label, value, color }) {
  return (
    <div>
      <div style={{
        fontSize: 9.5, fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.14em',
        color: '#64748b', marginBottom: 4,
      }}>
        {label}
      </div>
      <div style={{ fontFamily: 'JetBrains Mono', fontSize: 15, fontWeight: 700, color }}>
        {value}
      </div>
    </div>
  );
}

function GhostBtn({ children, onClick, disabled, title }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        padding: '8px 16px', borderRadius: 8,
        fontSize: 13, fontWeight: 600, color: '#fff',
        background: 'rgba(255,255,255,0.08)',
        boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.15)',
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
      }}
    >
      {children}
    </button>
  );
}
