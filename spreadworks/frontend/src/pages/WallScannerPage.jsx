// Wall Scanner — descriptive-only $/% distance to the nearest GEX call/put
// wall, per ticker (GME + 7 tickers flow-mix continuation was tested and
// FAILED on). NO directional fade/breakout call anywhere on this page — that
// door is closed (memory `flowmix-singlename-fails.md`), not a style choice.
// This page states where the walls sit and how far price is from them.
// Nothing predicts which way price goes when it gets there.
import { useEffect, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', GREY = '#9ca3af', DIM = '#8b93a7';

const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  banner: {
    display: 'flex', gap: 10, alignItems: 'flex-start',
    background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.35)',
    borderRadius: 10, padding: '12px 14px', marginBottom: 20, fontSize: 13,
    color: '#e8d9a8', lineHeight: 1.6,
  },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  table: { width: '100%', borderCollapse: 'collapse' },
  th: { textAlign: 'left', color: DIM, fontSize: 13, padding: '6px 10px', fontWeight: 600 },
  td: { padding: '8px 10px', fontSize: 13, borderTop: '1px solid #1c2233' },
  mono: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontVariantNumeric: 'tabular-nums' },
  tickerCell: { fontWeight: 700, fontSize: 14 },
  small: { fontSize: 13, color: DIM },
  errBox: { ...{ fontSize: 13, color: RED, padding: '10px 14px' } },
};

function money(x) {
  if (x == null) return '—';
  const sign = x < 0 ? '−' : '';
  return `${sign}$${Math.abs(x).toFixed(2)}`;
}
function pct(x) {
  if (x == null) return '—';
  return `${x.toFixed(2)}%`;
}

// Gap size colors the number only — never implies direction, just how close
// price already sits to that wall.
function gapColor(pctVal) {
  if (pctVal == null) return GREY;
  if (pctVal < 1) return RED;
  if (pctVal < 3) return AMBER;
  return GREEN;
}

function WallCell({ wall }) {
  if (!wall) return <span style={S.small}>no wall found</span>;
  return (
    <div>
      <div style={{ ...S.mono }}>{wall.strike}</div>
      <div style={{ ...S.mono, color: gapColor(wall.pct_to_break), fontSize: 13 }}>
        {money(wall.dollars_to_break)} ({pct(wall.pct_to_break)})
      </div>
    </div>
  );
}

export default function WallScannerPage() {
  const [payload, setPayload] = useState(null);
  const [err, setErr] = useState(null);
  const [loadedAt, setLoadedAt] = useState(null);

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
    const t = setInterval(load, 60 * 1000);
    return () => { live = false; clearInterval(t); };
  }, []);

  const rows = payload?.data || [];

  return (
    <div style={S.wrap}>
      <h1 style={S.h1}>Wall Scanner</h1>
      <p style={S.sub}>
        {rows.length ? `${rows.length} tickers` : 'Loading…'}
        {loadedAt && ` · updated ${loadedAt.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}`}
      </p>

      <div style={S.banner}>
        <AlertTriangle size={16} color={AMBER} style={{ flexShrink: 0, marginTop: 2 }} />
        <span>
          <b>Unvalidated, descriptive only.</b> GEX walls are NOT predicted turning
          points — this has been placebo-tested on SPY and, more recently, on
          single names, and neither held up. This page shows only where the
          largest call/put gamma concentration currently sits relative to spot,
          and the $ / % distance to it. It makes no directional call and should
          not be read as one.
        </span>
      </div>

      {err && <div style={S.errBox}>Failed to load: {err}</div>}

      <div style={S.card}>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>Ticker</th>
              <th style={S.th}>Spot</th>
              <th style={S.th}>Call wall (strike / $ / % to break)</th>
              <th style={S.th}>Put wall (strike / $ / % to break)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.ticker}>
                <td style={{ ...S.td, ...S.tickerCell }}>{row.ticker}</td>
                {row.available ? (
                  <>
                    <td style={{ ...S.td, ...S.mono }}>{money(row.spot)}</td>
                    <td style={S.td}><WallCell wall={row.call_wall} /></td>
                    <td style={S.td}><WallCell wall={row.put_wall} /></td>
                  </>
                ) : (
                  <td style={{ ...S.td, color: DIM }} colSpan={3}>data unavailable</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
