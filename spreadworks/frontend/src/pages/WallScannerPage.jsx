// Wall Scanner — descriptive-only $/% distance to the nearest GEX call/put
// wall, scanned across TradingVolatility's whole covered universe (liquid,
// optionable names — not a fixed basket; corrected 2026-09-11 after the
// original 8-ticker dashboard version). NO directional fade/breakout call
// anywhere on this page — that door is closed (memory
// `flowmix-singlename-fails.md`), not a style choice. This page states
// where the walls sit and how far price is from them, sorted tightest-gap
// first. Nothing predicts which way price goes when it gets there.
//
// 2026-09-11 redesign (Leron: "i have no idea how close it is to breaking i
// need money number and volume ... its very generic"): the old layout put
// call_wall and put_wall in two symmetric columns, making the viewer do the
// comparison themselves to find which one actually mattered. This version
// promotes the tighter of the two — closest_wall, already computed
// server-side as the sort key — to its own prominent, EXPLICITLY LABELED
// column (the unlabeled $/% pair was the next complaint: "i dont know what
// the dollar number or the % number means").
//
// Same day, "is there enough money to break the wall / is position building
// above or below it": added the 1-day options-implied expected move (is the
// $ distance to the wall even a plausible move today) and, expanding a row,
// the OTHER 1-2 concentrations per side (a second wall forming further out)
// plus a chart of this exact wall's OI/GEX over time — intraday points and,
// as the scheduled capture job (backend/__init__.py `wall_scanner_capture`)
// keeps running, day over day. History is EMPTY until that job has been
// running a while; this page never fabricates a trend it doesn't have data
// for.
import { Fragment, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Search, ChevronDown, ChevronRight } from 'lucide-react';
import {
  ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip, Legend,
} from 'recharts';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', GREY = '#9ca3af', DIM = '#8b93a7';
const LINE1 = '#60a5fa', LINE2 = '#c084fc';

const S = {
  wrap: { maxWidth: 1240, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  banner: {
    display: 'flex', gap: 10, alignItems: 'flex-start',
    background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.35)',
    borderRadius: 10, padding: '12px 14px', marginBottom: 20, fontSize: 13,
    color: '#e8d9a8', lineHeight: 1.6,
  },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  searchWrap: {
    display: 'flex', alignItems: 'center', gap: 8, background: '#0e1220',
    border: '1px solid #232a3d', borderRadius: 8, padding: '8px 12px', marginBottom: 16,
    maxWidth: 280,
  },
  searchInput: {
    background: 'transparent', border: 'none', outline: 'none', color: '#e6e9f2',
    fontSize: 13, width: '100%',
  },
  tableWrap: { overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { textAlign: 'left', color: DIM, fontSize: 13, padding: '6px 10px', fontWeight: 600, whiteSpace: 'nowrap' },
  td: { padding: '8px 10px', fontSize: 13, borderTop: '1px solid #1c2233', verticalAlign: 'top' },
  mono: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontVariantNumeric: 'tabular-nums' },
  tickerCell: { fontWeight: 700, fontSize: 14, whiteSpace: 'nowrap', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 },
  small: { fontSize: 13, color: DIM },
  errBox: { fontSize: 13, color: RED, padding: '10px 14px' },
  badge: {
    display: 'inline-block', fontSize: 11, fontWeight: 700, borderRadius: 4,
    padding: '1px 6px', marginRight: 6, letterSpacing: 0.3,
  },
  detailRow: { background: '#0e1220' },
  detailWrap: { padding: '14px 16px', display: 'flex', gap: 24, flexWrap: 'wrap' },
  detailCol: { minWidth: 220, flex: '1 1 220px' },
  detailTitle: { fontSize: 12, fontWeight: 700, color: DIM, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
};

function money(x, d = 2) {
  if (x == null) return '—';
  const sign = x < 0 ? '−' : '';
  return `${sign}$${Math.abs(x).toFixed(d)}`;
}
function pct(x) {
  if (x == null) return '—';
  return `${x.toFixed(2)}%`;
}
// Large dollar/share figures (GEX notional, open interest) — raw numbers
// like "6254823" are exactly the "generic" complaint; abbreviate to M/K.
function abbrev(x, prefix = '') {
  if (x == null) return '—';
  const sign = x < 0 ? '−' : '';
  const abs = Math.abs(x);
  if (abs >= 1e9) return `${sign}${prefix}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${prefix}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${prefix}${abs.toFixed(0)}`;
}
function fmtTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// Gap size colors the number only — never implies direction, just how close
// price already sits to that wall.
function gapColor(pctVal) {
  if (pctVal == null) return GREY;
  if (pctVal < 1) return RED;
  if (pctVal < 3) return AMBER;
  return GREEN;
}

function ClosestWallCell({ wall }) {
  if (!wall) return <span style={S.small}>no wall found</span>;
  const isCall = wall.side === 'call';
  return (
    <div>
      <span
        style={{
          ...S.badge,
          background: isCall ? 'rgba(52,211,153,0.15)' : 'rgba(248,113,113,0.15)',
          color: isCall ? GREEN : RED,
        }}
      >
        {isCall ? 'CALL' : 'PUT'}
      </span>
      <span style={S.mono}>strike {wall.strike}</span>
      <div style={{ ...S.mono, color: gapColor(wall.pct_to_break), fontSize: 15, fontWeight: 700, marginTop: 2 }}>
        {money(wall.dollars_to_break)} to break <span style={{ fontWeight: 400, fontSize: 13 }}>({pct(wall.pct_to_break)} away)</span>
      </div>
      {wall.vs_expected_move_1d != null && (
        <div style={S.small}>{wall.vs_expected_move_1d.toFixed(2)}× today's expected move</div>
      )}
      {wall.delta ? (
        <div style={S.small}>
          OI was {isCall ? abbrev(wall.delta.call_oi_then) : abbrev(wall.delta.put_oi_then)} as of {fmtTime(wall.delta.captured_at)} — compare to the OI column
        </div>
      ) : (
        <div style={S.small}>no history yet for this strike</div>
      )}
    </div>
  );
}

function OtherWallCell({ wall }) {
  if (!wall) return <span style={S.small}>—</span>;
  return (
    <div style={S.small}>
      {wall.strike} <span style={S.mono}>{money(wall.dollars_to_break)} ({pct(wall.pct_to_break)})</span>
    </div>
  );
}

function WallListDetail({ title, walls }) {
  if (!walls || walls.length <= 1) return null;
  return (
    <div>
      <div style={S.detailTitle}>{title}</div>
      {walls.slice(1).map((w, i) => (
        <div key={i} style={{ ...S.small, marginBottom: 4 }}>
          strike {w.strike} · <span style={S.mono}>{money(w.dollars_to_break)} ({pct(w.pct_to_break)})</span> · {abbrev(w.net_gex, '$')} GEX
        </div>
      ))}
    </div>
  );
}

function HistoryChart({ series }) {
  if (!series || series.length < 2) {
    return <div style={S.small}>Not enough history yet — the capture job writes a point every 5 min during market hours. Check back once it's had time to build up.</div>;
  }
  const data = series.map((p) => ({
    t: fmtTime(p.captured_at),
    netGex: p.net_gex,
    callOi: p.call_oi_sum,
    putOi: p.put_oi_sum,
  }));
  return (
    <ResponsiveContainer width="100%" height={160}>
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <XAxis dataKey="t" tick={{ fontSize: 11, fill: DIM }} minTickGap={40} />
        <YAxis yAxisId="oi" tick={{ fontSize: 11, fill: DIM }} width={50} />
        <Tooltip contentStyle={{ background: '#141824', border: '1px solid #232a3d', fontSize: 12 }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line yAxisId="oi" type="monotone" dataKey="callOi" stroke={GREEN} dot={false} name="Call OI" strokeWidth={1.5} />
        <Line yAxisId="oi" type="monotone" dataKey="putOi" stroke={RED} dot={false} name="Put OI" strokeWidth={1.5} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function RowDetail({ row }) {
  const [series, setSeries] = useState(null);
  const [loading, setLoading] = useState(true);
  const closest = row.closest_wall;

  useEffect(() => {
    let live = true;
    if (!closest) { setLoading(false); return; }
    setLoading(true);
    fetch(`${API_URL}/api/spreadworks/wall-scanner/${row.ticker}/history?side=${closest.side}&strike=${closest.strike}&days=5`)
      .then((r) => r.json())
      .then((d) => { if (live) { setSeries(d.series || []); setLoading(false); } })
      .catch(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [row.ticker, closest?.side, closest?.strike]);

  return (
    <tr style={S.detailRow}>
      <td colSpan={7} style={{ ...S.td, borderTop: '1px solid #232a3d' }}>
        <div style={S.detailWrap}>
          <div style={{ ...S.detailCol, minWidth: 320, flex: '2 1 320px' }}>
            <div style={S.detailTitle}>
              Closest wall history (intraday + day-over-day, last 5 days)
            </div>
            {loading ? <span style={S.small}>Loading…</span> : <HistoryChart series={series} />}
          </div>
          <div style={S.detailCol}>
            <WallListDetail title="Other call concentrations" walls={row.call_walls} />
            <WallListDetail title="Other put concentrations" walls={row.put_walls} />
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function WallScannerPage() {
  const [payload, setPayload] = useState(null);
  const [err, setErr] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);
  const [q, setQ] = useState('');
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let live = true;
    const load = async () => {
      try {
        const r = await fetch(`${API_URL}/api/spreadworks/wall-scanner`);
        const d = await r.json();
        if (live) { setPayload(d); setLoadedAt(new Date()); setErr(null); }
      } catch (e) { if (live) setErr(String(e)); }
    };
    load();
    // A full scan is a cached ~100-call pass server-side (5 min TTL, and the
    // scheduled capture job keeps it warm) — no point polling faster.
    const t = setInterval(load, 5 * 60 * 1000);
    return () => { live = false; clearInterval(t); };
  }, []);

  const allRows = payload?.data || [];
  const rows = useMemo(() => {
    const needle = q.trim().toUpperCase();
    if (!needle) return allRows;
    return allRows.filter((r) => r.ticker.includes(needle));
  }, [allRows, q]);

  return (
    <div style={S.wrap}>
      <h1 style={S.h1}>Wall Scanner</h1>
      <p style={S.sub}>
        {payload
          ? `${payload.tickers_scanned || allRows.length} tickers scanned, sorted tightest-gap-first`
          : 'Scanning…'}
        {payload?.elapsed_sec != null && ` · ${payload.elapsed_sec}s`}
        {loadedAt && ` · updated ${loadedAt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}`}
        {' · auto-refreshes every 5 min'}
      </p>

      <div style={S.banner}>
        <AlertTriangle size={16} color={AMBER} style={{ flexShrink: 0, marginTop: 2 }} />
        <span>
          <b>Unvalidated, descriptive only.</b> GEX walls are NOT predicted turning
          points — this has been placebo-tested on SPY and, more recently, on
          single names, and neither held up. "Closest wall" is the tighter of
          the call/put gap; the $ and % under it are how far spot has to move
          to reach that strike. Expected-move ratio, OI, and the history chart
          (click a ticker) are all size/liquidity/build-up context — none of
          it is a forecast of whether the wall holds or breaks.
        </span>
      </div>

      {err && <div style={S.errBox}>Failed to load: {err}</div>}

      <div style={S.searchWrap}>
        <Search size={14} color={DIM} />
        <input
          style={S.searchInput}
          placeholder="Filter ticker…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>

      <div style={S.card}>
        <div style={S.tableWrap}>
          <table style={S.table}>
            <thead>
              <tr>
                <th style={S.th}>Ticker</th>
                <th style={S.th}>Spot</th>
                <th style={S.th}>Closest wall ($ / % to break)</th>
                <th style={S.th}>$ GEX at wall</th>
                <th style={S.th}>Open interest (C / P)</th>
                <th style={S.th}>$ per 1% move</th>
                <th style={S.th}>Other wall</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isOpen = expanded === row.ticker;
                return (
                  <Fragment key={row.ticker}>
                    <tr>
                      <td
                        style={{ ...S.td, ...S.tickerCell }}
                        onClick={() => row.available && setExpanded(isOpen ? null : row.ticker)}
                        title={row.available ? 'Click for history + other strikes' : undefined}
                      >
                        {row.available && (isOpen ? <ChevronDown size={13} color={DIM} /> : <ChevronRight size={13} color={DIM} />)}
                        {row.ticker}
                      </td>
                      {row.available ? (
                        <>
                          <td style={{ ...S.td, ...S.mono }}>{money(row.spot)}</td>
                          <td style={S.td}><ClosestWallCell wall={row.closest_wall} /></td>
                          <td style={{ ...S.td, ...S.mono }}>{abbrev(row.closest_wall?.net_gex, '$')}</td>
                          <td style={{ ...S.td, ...S.mono }}>
                            {abbrev(row.call_oi_sum)} / {abbrev(row.put_oi_sum)}
                            {row.put_call_oi != null && (
                              <div style={S.small}>P/C {row.put_call_oi.toFixed(2)}</div>
                            )}
                          </td>
                          <td style={{ ...S.td, ...S.mono }}>{abbrev(row.gex_value_per_1pct, '$')}</td>
                          <td style={S.td}>
                            <OtherWallCell
                              wall={row.closest_wall?.side === 'call' ? row.put_wall : row.call_wall}
                            />
                          </td>
                        </>
                      ) : (
                        <td style={{ ...S.td, color: DIM }} colSpan={6}>data unavailable</td>
                      )}
                    </tr>
                    {isOpen && <RowDetail row={row} />}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
