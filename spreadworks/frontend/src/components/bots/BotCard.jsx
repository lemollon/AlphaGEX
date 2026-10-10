// The one bot-card component. Every card on /bots — including REFLEX's
// spotlight card (see ReflexSpotlightCard.jsx) — renders through this file.
// Do not fork a second copy of this JSX: a bot with no live row/botStats data
// (new bot, or a bot that lives outside this repo like REFLEX) still goes
// through the SAME header/headline/footer slots, just with a handful of
// optional override props so it can say something honest instead of
// rendering a live number it doesn't have.
//
// Extracted out of FleetPage.jsx 2026-10-05 so REFLEX could use the literal
// component instead of a hand-maintained lookalike that silently drifted.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import BotGlyph from './BotGlyph';
import { BOT_REGISTRY, BOT_THEME, STRATEGY_LABEL } from '../../lib/botRegistry';

export const GREEN = '#34d399';
export const RED = '#fb7185';
export const AMBER = '#fbbf24';
export const MUTED = '#64748b';

// A bot's last scan is STALE if it's older than this AND the market is open
// (last_scan_at naturally trails while the market is closed — that's not a
// problem, so the alarm is gated on isOpen).
export const STALE_MS = 20 * 60 * 1000;

export function money(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return '$' + Math.round(Math.abs(n)).toLocaleString('en-US');
}

// Signed money with a true unicode minus, matching the bot dropdown's format.
export function signedMoney(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  if (Math.round(n) === 0) return '$0';
  return (n > 0 ? '+' : '−') + money(n);
}

function signedPct(n) {
  if (typeof n !== 'number' || !Number.isFinite(n)) return null;
  return (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(1) + '%';
}

export function pnlColor(n) {
  if (typeof n !== 'number' || !Number.isFinite(n) || Math.round(n) === 0) return MUTED;
  return n > 0 ? GREEN : RED;
}

// The API returns NAIVE timestamps that are actually UTC ("2026-08-07
// 20:10:00.000947" while the server clock reads 20:10Z). `new Date(str)` on a
// naive string parses it as BROWSER-LOCAL, so in CT that reads 5h in the
// future, the diff goes negative, and the caller prints "just now" — forever,
// no matter how long ago the bot really scanned. That defeats the entire point
// of showing it on a fleet page, where a frozen scan clock is the main symptom
// of a dead bot. Pin the string to UTC before parsing.
//
// NOTE: relativeTime() in BotDashboard.jsx and PositionsTab.jsx still has the
// uncorrected version, so their "scanned …" labels understate staleness.
export function parseTs(ts) {
  if (ts instanceof Date || typeof ts === 'number') return new Date(ts);
  const s = String(ts).trim();
  // Already carries a zone (…Z / +00:00) — trust it. Otherwise mark it UTC.
  const zoned = /(?:Z|[+-]\d{2}:?\d{2})$/.test(s);
  return new Date(zoned ? s : s.replace(' ', 'T') + 'Z');
}

export function relativeTime(ts) {
  if (!ts) return '—';
  const at = parseTs(ts);
  if (Number.isNaN(at.getTime())) return '—';
  const diff = Math.floor((Date.now() - at.getTime()) / 1000);
  if (diff < 0) return 'just now';
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function capitalize(s) {
  return String(s || '').charAt(0) + String(s || '').slice(1).toLowerCase();
}

// A bot the API knows about but the frontend registry doesn't (backend shipped
// first) still gets a readable card instead of crashing on BOT_THEME[id].glyph.
const FALLBACK_THEME = {
  glyph: 'wave',
  primary: '#94a3b8',
  primarySoft: 'rgba(148,163,184,0.10)',
  primaryRing: 'rgba(148,163,184,0.30)',
  glow: 'rgba(148,163,184,0.18)',
};

export const LABEL_STYLE = {
  fontSize: 9, fontWeight: 600, letterSpacing: '0.08em',
  textTransform: 'uppercase', color: MUTED,
};

/* ── fleet-stats micro-widgets (sparkline / trades / drawdown / account) ── */

// Plain inline SVG, no recharts — 23 of these on one page is 23 chart-lib
// instances too many. viewBox + preserveAspectRatio="none" stretches to
// whatever box the caller gives it.
function Sparkline({ series }) {
  if (!Array.isArray(series) || series.length < 2) return null;
  const w = 100, h = 28;
  const vals = series.map(p => p.equity);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const step = w / (vals.length - 1);
  const points = vals
    .map((v, i) => `${(i * step).toFixed(2)},${(h - ((v - min) / range) * h).toFixed(2)}`)
    .join(' ');
  const color = vals[vals.length - 1] >= vals[0] ? GREEN : RED;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      style={{ width: '100%', height: h, display: 'block' }}
    >
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function TradesLine({ trades }) {
  if (!trades) return null;
  const style = { fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 4 };
  if (trades.n === 0) return <div style={style}>no closed trades yet</div>;
  const wr = trades.win_rate != null ? Math.round(trades.win_rate * 100) + '%' : '—';
  return (
    <div style={style}>
      {wr} win · {trades.n} trade{trades.n === 1 ? '' : 's'} · 7d {signedMoney(trades.pnl_7d)} · 30d {signedMoney(trades.pnl_30d)}
    </div>
  );
}

function DrawdownChip({ pct }) {
  if (typeof pct !== 'number' || !Number.isFinite(pct) || pct < 0.03) return null;
  const severe = pct >= 0.10;
  const color = severe ? RED : AMBER;
  return (
    <span
      style={{
        marginLeft: 6, fontSize: 9, fontWeight: 700, padding: '1px 6px', borderRadius: 9999,
        color, background: severe ? 'rgba(251,113,133,0.12)' : 'rgba(251,191,36,0.12)',
        boxShadow: `inset 0 0 0 1px ${color}55`,
      }}
    >
      DD -{Math.round(pct * 100)}%
    </span>
  );
}

// Registry #23b's pre-calibrated health bands (EBB) — a rolling-window
// verdict on whether the paper record is still tracking the validated edge.
// See routes_bots._bot_health for the thresholds.
const HEALTH_COLOR = { SHARP: GREEN, WATCH: AMBER, DEGRADED: RED, warming_up: MUTED };
const HEALTH_LABEL = { SHARP: 'Sharp', WATCH: 'Watch', DEGRADED: 'Degraded', warming_up: 'Warming up' };

function healthNum(n) {
  return typeof n === 'number' && Number.isFinite(n) ? Math.round(n) : '—';
}

function HealthChip({ health }) {
  if (!health || !health.status) return null;
  const color = HEALTH_COLOR[health.status] || MUTED;
  const label = HEALTH_LABEL[health.status] || health.status;
  return (
    <span
      title={
        `60-trade $${healthNum(health.roll60)} · 120-trade $${healthNum(health.roll120)} `
        + `· 20-trade credit $${healthNum(health.credit20)}`
      }
      style={{
        flexShrink: 0, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
        textTransform: 'uppercase', padding: '2px 7px', borderRadius: 9999,
        color, background: 'transparent',
        boxShadow: `inset 0 0 0 1px ${color}55`,
      }}
    >
      {label}
    </span>
  );
}

function AccountChip({ account }) {
  const isPaper = !account || account === 'paper';
  return (
    <span
      style={{
        flexShrink: 0, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
        textTransform: 'uppercase', padding: '2px 7px', borderRadius: 9999,
        color: isPaper ? AMBER : RED,
        background: isPaper ? 'transparent' : 'rgba(251,113,133,0.10)',
        boxShadow: `inset 0 0 0 1px ${isPaper ? AMBER : RED}55`,
      }}
    >
      {isPaper ? 'PAPER' : 'LIVE $'}
    </span>
  );
}

/* ── one bot card ────────────────────────────────────────────────── */
//
// Override props (all optional — omit every one of them and this renders
// EXACTLY what FleetPage always rendered). They exist so a bot with no
// row/botStats data — REFLEX today, a brand-new bot tomorrow — can still use
// this component instead of a second hand-built JSX tree:
//
//   linkTo            — where the card navigates (default `/bots/{id}`)
//   statusOverride     — { label, color } replaces the Live/Paused pill
//   accountOverride    — { label, color } replaces the Paper/Live $ chip
//   headline           — { label, value, color, sub } replaces the whole
//                         "Today" block (skips the today/realized math)
//   footer             — [{ label, value, color, title }, × 3] replaces the
//                         Total/Equity/Open 3-col grid
//   atRiskText         — string, forces the "At risk" line even with no
//                         botStats (default: only shown when botStats exists)
//   scanText           — string, replaces "scanned Xm ago" on the bottom row
export default function BotCard({
  row, botStats, isOpen,
  linkTo, statusOverride, accountOverride, headline, footer, atRiskText, scanText,
}) {
  const id = row.bot;
  const meta = BOT_REGISTRY[id] || {};
  const theme = BOT_THEME[id] || FALLBACK_THEME;
  const [hover, setHover] = useState(false);

  const display = capitalize(row.display || meta.display || id);
  const strategy = row.strategy || meta.strategy;
  // WHICH TICKER IS THIS BOT TRADING. The registry answer is static and says
  // "multi" for UNDERTOW/DELTA, which is true and useless. Prefer the tickers
  // the bot is actually holding right now; fall back to the registry when flat.
  const liveTickers = botStats?.tickers || [];
  const tickerLabel = liveTickers.length
    ? liveTickers.join(' · ')
    : (meta.ticker && meta.ticker !== 'multi' ? meta.ticker : (meta.ticker || '—'));
  const tickerIsLive = liveTickers.length > 0;
  const failed = !!row.error;

  // Live day P&L = realized closes + mark-to-market on the open book. Realized
  // alone sits at $0 until something actually closes, which reads as a dead bot
  // while it's holding — same reasoning as the nav dropdown's rows.
  const realized = typeof row.today_pnl === 'number' ? row.today_pnl : null;
  const unreal = typeof row.unrealized_pnl === 'number' ? row.unrealized_pnl : 0;
  const today = realized == null ? null : realized + unreal;

  // Total P&L is measured against starting_capital using the MARK-TO-MARKET
  // equity, so an open position shows up here too. equity_mtm is what the bot's
  // own dashboard tile reads; `equity` is realized-only (the scanner sizes off
  // it and must not lever up on unrealized marks).
  const start = typeof row.starting_capital === 'number' ? row.starting_capital : null;
  const mtm = typeof row.equity_mtm === 'number'
    ? row.equity_mtm
    : typeof row.equity === 'number' ? row.equity + unreal : null;
  const total = start != null && mtm != null ? mtm - start : null;
  const retPct = total != null && start ? (total / start) * 100 : null;

  const openPos = typeof row.open_positions === 'number' ? row.open_positions : null;
  const enabled = !!row.enabled;

  const account = botStats && !botStats.error ? botStats.account : 'paper';

  // After-hours framing: the market is closed and today's number is a flat
  // $0 (nothing realized, nothing open to mark) — that reads as a dead bot
  // when what actually happened was yesterday's session. Swap the headline
  // to the last completed session instead, when we have one.
  const lastSession = botStats && !botStats.error ? botStats.last_session : null;
  const showLastSession = !isOpen && today != null && Math.round(today) === 0 && !!lastSession;
  const headlineLabel = showLastSession ? `Last session (${lastSession.d})` : 'Today';
  const headlineValue = showLastSession ? lastSession.pnl : today;

  // Scan-staleness alarm — only meaningful while the market is open; a
  // last_scan_at from yesterday afternoon is expected once the bell rings.
  const scanAt = row.last_scan_at ? parseTs(row.last_scan_at) : null;
  const scanAgeMs = scanAt && !Number.isNaN(scanAt.getTime()) ? Date.now() - scanAt.getTime() : null;
  const stale = isOpen && scanAgeMs != null && scanAgeMs > STALE_MS;

  return (
    <Link
      to={linkTo || `/bots/${id}`}
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
          ? `inset 0 0 0 1px ${theme.primaryRing}, 0 10px 30px -12px ${theme.glow || 'rgba(0,0,0,0.4)'}`
          : 'inset 0 0 0 1px rgba(125,211,252,0.08)',
      }}
    >
      {/* header — glyph, name, strategy, live/paused */}
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
            {display}
          </div>
          <div
            className="truncate"
            style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}
          >
            {STRATEGY_LABEL[strategy] || strategy || '—'}
          </div>
          {/* The ticker used to live in the 9.5px footer next to the version
              string and the scan timestamp -- the least prominent thing on the
              card, read as chrome. "What does this bot trade" is a primary
              question, so it sits under the name. */}
          <div style={{ marginTop: 4 }}>
            <span style={{
              fontFamily: 'JetBrains Mono', fontSize: 10, fontWeight: 700,
              padding: '2px 6px', borderRadius: 5, letterSpacing: 0.3,
              background: tickerIsLive ? theme.primarySoft : 'rgba(125,211,252,0.06)',
              color: tickerIsLive ? theme.primary : MUTED,
              boxShadow: `inset 0 0 0 1px ${tickerIsLive ? theme.primaryRing : 'rgba(125,211,252,0.10)'}`,
            }}
            title={tickerIsLive
              ? `Currently holding ${tickerLabel}`
              : 'No open positions — ticker from the bot registry'}>
              {tickerLabel}
            </span>
          </div>
        </div>

        {statusOverride ? (
          <span
            className="flex items-center gap-1.5"
            style={{
              flexShrink: 0,
              fontSize: 9.5, fontWeight: 700, letterSpacing: '0.10em',
              textTransform: 'uppercase',
              padding: '3px 8px', borderRadius: 9999,
              color: statusOverride.color,
              background: `${statusOverride.color}1a`,
              boxShadow: `inset 0 0 0 1px ${statusOverride.color}55`,
            }}
          >
            <span style={{ width: 5, height: 5, borderRadius: 9999, background: statusOverride.color }} />
            {statusOverride.label}
          </span>
        ) : (
          <span
            className="flex items-center gap-1.5"
            style={{
              flexShrink: 0,
              fontSize: 9.5, fontWeight: 700, letterSpacing: '0.10em',
              textTransform: 'uppercase',
              padding: '3px 8px', borderRadius: 9999,
              color: enabled ? GREEN : MUTED,
              background: enabled ? 'rgba(52,211,153,0.10)' : 'rgba(148,163,184,0.08)',
              boxShadow: `inset 0 0 0 1px ${enabled ? 'rgba(52,211,153,0.25)' : 'rgba(148,163,184,0.18)'}`,
            }}
          >
            <span
              style={{ width: 5, height: 5, borderRadius: 9999, background: enabled ? GREEN : '#475569' }}
            />
            {enabled ? 'Live' : 'Paused'}
          </span>
        )}

        {accountOverride ? (
          <span
            style={{
              flexShrink: 0, fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
              textTransform: 'uppercase', padding: '2px 7px', borderRadius: 9999,
              color: accountOverride.color,
              background: 'transparent',
              boxShadow: `inset 0 0 0 1px ${accountOverride.color}55`,
            }}
          >
            {accountOverride.label}
          </span>
        ) : (
          <AccountChip account={account} />
        )}
        {!statusOverride && botStats && !botStats.error && <HealthChip health={botStats.health} />}
      </div>

      {failed ? (
        <div
          className="flex items-start gap-2 rounded-lg"
          style={{
            padding: '8px 12px',
            background: 'rgba(251,113,133,0.08)',
            boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.22)',
          }}
        >
          <AlertTriangle size={13} style={{ color: RED, flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 11, color: '#fda4af', wordBreak: 'break-word' }}>{row.error}</div>
        </div>
      ) : (
        <>
          {/* headline — the big number under the glyph row */}
          <div>
            <div style={{ ...LABEL_STYLE, fontSize: 9.5, letterSpacing: '0.10em' }}>
              {headline ? headline.label : headlineLabel}
            </div>
            <div
              style={{
                fontFamily: 'JetBrains Mono', fontSize: 26, fontWeight: 700,
                lineHeight: 1.15, marginTop: 2,
                color: headline ? (headline.color || GREEN) : pnlColor(headlineValue),
              }}
            >
              {headline ? headline.value : (headlineValue == null ? '—' : signedMoney(headlineValue))}
            </div>
            {headline ? (
              headline.sub && (
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}>
                  {headline.sub}
                </div>
              )
            ) : (
              !showLastSession && unreal !== 0 && (
                <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED, marginTop: 2 }}>
                  {signedMoney(realized)} realized · {signedMoney(unreal)} open
                </div>
              )
            )}
          </div>

          {botStats && !botStats.error && (
            <>
              <Sparkline series={botStats.equity_series} />
              <TradesLine trades={botStats.trades} />
            </>
          )}

          {/* total / equity / open */}
          <div
            className="grid grid-cols-3 gap-2"
            style={{ paddingTop: 12, borderTop: '1px solid rgba(125,211,252,0.08)' }}
          >
            {footer ? (
              footer.map((col, i) => (
                <div className="min-w-0" key={i} title={col.title}>
                  <div style={LABEL_STYLE}>{col.label}</div>
                  <div
                    className="truncate"
                    style={{
                      fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700,
                      marginTop: 2, color: col.color || '#e2e8f0',
                    }}
                  >
                    {col.value}
                  </div>
                </div>
              ))
            ) : (
              <>
                <div className="min-w-0">
                  <div style={LABEL_STYLE}>Total</div>
                  <div
                    className="truncate"
                    style={{
                      fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700,
                      marginTop: 2, color: pnlColor(total),
                    }}
                  >
                    {total == null ? '—' : signedMoney(total)}
                  </div>
                  {retPct != null && (
                    <div style={{ fontFamily: 'JetBrains Mono', fontSize: 9.5, color: MUTED }}>
                      {signedPct(retPct)}
                    </div>
                  )}
                </div>

                <div className="min-w-0">
                  <div style={LABEL_STYLE}>Equity</div>
                  <div
                    className="truncate flex items-center"
                    style={{
                      fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700,
                      marginTop: 2, color: '#e2e8f0',
                    }}
                  >
                    {money(mtm)}
                    {botStats && !botStats.error && <DrawdownChip pct={botStats.drawdown_pct} />}
                  </div>
                </div>

                <div className="min-w-0">
                  <div style={LABEL_STYLE}>Open</div>
                  <div
                    style={{
                      fontFamily: 'JetBrains Mono', fontSize: 13, fontWeight: 700,
                      marginTop: 2, color: openPos ? theme.primary : MUTED,
                    }}
                  >
                    {openPos == null ? '—' : openPos}
                  </div>
                </div>
              </>
            )}
          </div>

          {atRiskText ? (
            <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED }}>
              {atRiskText}
            </div>
          ) : botStats && !botStats.error && (
            <div style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: MUTED }}>
              {botStats.risk?.open_max_loss != null
                ? `At risk ${money(botStats.risk.open_max_loss)}`
                : 'At risk —'}
              {botStats.risk?.nearest_dte != null && ` · nearest exp ${botStats.risk.nearest_dte} DTE`}
            </div>
          )}
        </>
      )}

      {/* footer — ticker · version · last scan */}
      <div
        className="flex items-center justify-between gap-2"
        style={{
          marginTop: 'auto', paddingTop: 8,
          borderTop: '1px solid rgba(125,211,252,0.06)',
          fontFamily: 'JetBrains Mono', fontSize: 9.5, color: MUTED,
        }}
      >
        <span className="truncate">
          {meta.version || ''}
        </span>
        <span className="truncate" style={{ flexShrink: 0, color: !scanText && stale ? RED : MUTED }}>
          {scanText || `${stale ? '⚠ STALE · ' : ''}scanned ${relativeTime(row.last_scan_at)}`}
        </span>
      </div>
    </Link>
  );
}
