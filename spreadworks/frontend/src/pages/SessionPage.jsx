// Session — the live intraday tape. Distinct from every other page here:
// /risk and /squeeze answer "what is today's regime", decided once from the
// prior close. This answers "what is happening RIGHT NOW".
//
// It exists because the 2026-08-17 miss was invisible in real time. SPY slid
// 775.50 -> 772.51 over 80 minutes, the watchers were running, and no single
// view put price, the flow z, the fixed clocks and the confirmation state on
// one clock. Reconstructing that session afterwards took four tables and an
// external price API.
//
// Two deliberate omissions:
//   * NO gamma/GEX panel. gamma_history writes ~280 rows a day holding 3
//     distinct values (spot froze at 775.80 on 08-17 while SPY traded to
//     772.51). A chart of it would look authoritative and be wrong, so the
//     page reports the feed as dead instead of drawing it.
//   * NO verdict. /risk and /squeeze own that. Two surfaces disagreeing about
//     the same call is worse than one surface.
//
// Charts are hand-rolled SVG on purpose — Recharts writes an absolute pixel
// width from its first measurement and drags the whole page sideways on
// mobile (see the squeeze page notes).
//
// All spacing inline (Tailwind p-*/m-* are zeroed app-wide).
import { useEffect, useState, useCallback } from 'react';
import { Radio, ArrowDown, ArrowUp } from 'lucide-react';
import { API_URL } from '../lib/api';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', BLUE = '#60a5fa', DIM = '#8b93a7';
const S = {
  wrap: { maxWidth: 1100, margin: '0 auto', padding: '24px 16px 96px' },
  h1: { fontSize: 22, fontWeight: 700, margin: '0 0 4px' },
  sub: { color: DIM, fontSize: 13, margin: '0 0 20px' },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 16, marginBottom: 16 },
  cardTitle: { fontSize: 13, fontWeight: 700, marginBottom: 10 },
  small: { fontSize: 11, color: DIM },
  mono: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontVariantNumeric: 'tabular-nums' },
};

const ctLabel = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
const num = (x, d = 2) => (x == null || Number.isNaN(x) ? '—' : Number(x).toFixed(d));

// z-score -> colour. Only ±2 is a threshold anywhere in this system; 1.5 arms
// the confirmation watcher. Anything below reads as ordinary and must not be
// coloured like a signal.
function zColor(z) {
  if (z == null) return DIM;
  if (z > 2) return RED;
  if (z > 1.5) return AMBER;
  return DIM;
}

function Pill({ text, color, solid }) {
  return (
    <span style={{
      display: 'inline-block', padding: '3px 9px', borderRadius: 999, fontSize: 11,
      fontWeight: 700, letterSpacing: '.04em', whiteSpace: 'nowrap',
      color: solid ? '#0b0e17' : color, background: solid ? color : `${color}22`,
      border: `1px solid ${color}${solid ? '' : '55'}`,
    }}>{text}</span>
  );
}

// ── The price tape. Draws the 10:00 reference and BOTH confirmation
// thresholds, so the distance still to travel is readable at a glance rather
// than inferred from numbers.
function Tape({ tape, levels, confirm }) {
  const pts = (tape || []).filter((r) => r.spot != null);
  if (pts.length < 2) {
    return <div style={{ ...S.small, padding: '28px 0', textAlign: 'center' }}>
      Tape starts at 10:10 CT — {pts.length === 0 ? 'no points yet today' : 'one point so far'}.
    </div>;
  }
  const W = 900, H = 240, ml = 52, mr = 14, mt = 14, mb = 26;
  const iw = W - ml - mr, ih = H - mt - mb;
  const vals = pts.map((p) => p.spot)
    .concat([levels?.down, levels?.up, confirm?.ref_spot].filter((v) => v != null));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = Math.max((hi - lo) * 0.15, 0.25);
  lo -= pad; hi += pad;
  const m0 = pts[0].minute_ct, m1 = pts[pts.length - 1].minute_ct;
  const X = (m) => ml + (m1 === m0 ? iw / 2 : ((m - m0) / (m1 - m0)) * iw);
  const Y = (v) => mt + ((hi - v) / (hi - lo)) * ih;
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.minute_ct).toFixed(1)} ${Y(p.spot).toFixed(1)}`).join(' ');
  const line = (v, color, label, dash) => v == null ? null : (
    <g key={label}>
      <line x1={ml} y1={Y(v)} x2={W - mr} y2={Y(v)} stroke={color} strokeWidth="1"
            strokeDasharray={dash || undefined} opacity=".8" />
      <text x={ml - 7} y={Y(v) + 3.5} textAnchor="end" fill={color}
            style={{ fontSize: 10, ...S.mono }}>{num(v)}</text>
      <text x={W - mr} y={Y(v) - 5} textAnchor="end" fill={color}
            style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: '.08em' }}>{label}</text>
    </g>
  );
  const last = pts[pts.length - 1];
  return (
    <div style={{ overflowX: 'auto', minWidth: 0 }}>
      <svg width={W} height={H} role="img"
           aria-label="SPY price since the 10:00 CT reference, with the confirmation thresholds marked">
        {line(levels?.up, GREEN, 'UP TRIGGER', '4 3')}
        {line(confirm?.ref_spot, DIM, '10:00 REF', '2 3')}
        {line(levels?.down, RED, 'DOWN TRIGGER', '4 3')}
        <path d={d} fill="none" stroke="#e6e9f0" strokeWidth="1.7" strokeLinejoin="round" />
        {confirm?.fired_spot != null && (
          <circle cx={X(pts.reduce((b, p) =>
                    Math.abs(p.spot - confirm.fired_spot) < Math.abs(b.spot - confirm.fired_spot) ? p : b).minute_ct)}
                  cy={Y(confirm.fired_spot)} r="5" fill={confirm.fired_dir === 'DOWN' ? RED : GREEN} />
        )}
        <circle cx={X(last.minute_ct)} cy={Y(last.spot)} r="3.5" fill="#e6e9f0" />
        <text x={ml} y={H - 8} fill={DIM} style={{ fontSize: 10, ...S.mono }}>{ctLabel(m0)}</text>
        <text x={W - mr} y={H - 8} textAnchor="end" fill={DIM}
              style={{ fontSize: 10, ...S.mono }}>{ctLabel(m1)} CT</text>
      </svg>
    </div>
  );
}

export default function SessionPage() {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(() => {
    fetch(`${API_URL}/api/spreadworks/risk-advisor/session`)
      .then((r) => r.json()).then(setD).catch((e) => setErr(String(e)));
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  if (err) return <div style={S.wrap}><div style={S.card}>Couldn’t load the session: {err}</div></div>;
  if (!d) return <div style={S.wrap}><div style={S.card}>Loading…</div></div>;

  const c = d.confirm || {};
  const live = d.clock?.live;
  const fired = !!c.fired_dir;
  const dirColor = c.fired_dir === 'DOWN' ? RED : GREEN;

  // The headline. Priority order matters: a FIRED call outranks everything,
  // then armed-and-waiting, then the quiet state. Never lead with the quiet
  // state while a call is live on the same page.
  let head, headColor, headBody;
  if (fired) {
    head = `${c.fired_dir} CONFIRMED`;
    headColor = dirColor;
    headBody = `SPY broke ${c.fired_dir.toLowerCase()} through ${num(c.fired_dir === 'DOWN' ? d.levels?.down : d.levels?.up)} at a session ${c.fired_dir === 'DOWN' ? 'low' : 'high'}, from a ${num(c.ref_spot)} reference. On days flagged by the morning flow mix, that break keeps going 63% of the time versus a 50% coin flip otherwise.`;
  } else if (c.armed) {
    head = 'ARMED — WAITING FOR A SIDE';
    headColor = AMBER;
    headBody = `This morning's put/call mix was ${num(c.putcall_z, 1)}σ — unusual enough that a bigger-than-normal move is likely, but the direction is a coin flip until price commits. Watching for a break through ${num(d.levels?.down)} or ${num(d.levels?.up)}.`;
  } else if (c.armed === false) {
    head = 'NOT ARMED';
    headColor = DIM;
    headBody = `Morning flow mix was ordinary (${num(c.putcall_z, 1)}σ). A price break today carries no more information than a coin flip, so this page will stay quiet whatever SPY does.`;
  } else {
    head = 'WAITING FOR THE 10:00 SNAPSHOT';
    headColor = DIM;
    headBody = 'The morning flow reading is captured between 10:00 and 10:35 CT. Nothing here can arm before then.';
  }

  return (
    <div style={S.wrap}>
      <h1 style={S.h1}>Session</h1>
      <p style={S.sub}>
        What is happening right now. The regime call lives on Risk and Squeeze — this is the tape.
      </p>

      {/* clock / freshness — says FROZEN rather than implying live */}
      <div style={{ ...S.card, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Radio size={15} color={live ? GREEN : DIM} />
        <Pill text={d.clock?.state} color={live ? GREEN : DIM} solid={live} />
        <span style={S.small}>
          {live ? 'Watchers poll every 10 minutes, 10:10–14:00 CT. This page refreshes every 30s.'
                : d.clock?.detail}
        </span>
      </div>

      {/* THE CALL */}
      <div style={{ ...S.card, borderColor: `${headColor}66`, background: `${headColor}0d` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          {fired && (c.fired_dir === 'DOWN'
            ? <ArrowDown size={20} color={RED} /> : <ArrowUp size={20} color={GREEN} />)}
          <span style={{ fontSize: 20, fontWeight: 700, color: headColor, letterSpacing: '-.01em' }}>{head}</span>
          {fired && c.fired_at && (
            <span style={{ ...S.small, ...S.mono }}>
              {String(c.fired_at).slice(11, 16)} CT · {num(c.fired_spot)}
            </span>
          )}
        </div>
        <p style={{ fontSize: 14, lineHeight: 1.6, color: '#c6cbd8', margin: 0, maxWidth: '62ch' }}>
          {headBody}
        </p>
        {fired && (
          <p style={{ fontSize: 14, lineHeight: 1.6, color: '#e6e9f0', margin: '10px 0 0', maxWidth: '62ch' }}>
            <b>In plain English:</b> the market has picked a side and today it tends to stay picked.
            If you are short {c.fired_dir === 'DOWN' ? 'put' : 'call'} premium into this you are on the
            wrong side of it — that is the position to reduce or close. Don’t add.
          </p>
        )}
        <p style={{ ...S.small, margin: '10px 0 0' }}>
          Advisory. No bot reads this page — nothing here has moved a position.
        </p>
      </div>

      {/* the tape */}
      <div style={S.card}>
        <div style={S.cardTitle}>SPY since the 10:00 CT reference</div>
        <Tape tape={d.tape} levels={d.levels} confirm={c} />
        <div style={{ ...S.small, marginTop: 8 }}>
          Session range since the reference: {num(c.run_min)} – {num(c.run_max)}.
          A break only counts at a session extreme, so a dip that recovers doesn’t arm the rest of the day.
        </div>
      </div>

      {/* fixed clocks */}
      <div style={S.card}>
        <div style={S.cardTitle}>Flow clocks</div>
        <div style={{ display: 'grid', gap: 8 }}>
          {(d.clocks || []).map((k) => (
            <div key={k.clock} style={{
              display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
              padding: '8px 10px', borderRadius: 8,
              background: k.flagged ? `${RED}14` : '#0e1220',
              border: `1px solid ${k.flagged ? `${RED}44` : '#1c2233'}`,
            }}>
              <span style={{ ...S.mono, fontWeight: 700, width: 46 }}>{k.clock}</span>
              {!k.captured
                ? <span style={S.small}>not captured yet</span>
                : (<>
                    <span style={{ fontSize: 12, color: zColor(k.putv_z) }}>
                      put <b style={S.mono}>{num(k.putv_z, 1)}</b>
                    </span>
                    <span style={{ fontSize: 12, color: zColor(k.totv_z) }}>
                      total <b style={S.mono}>{num(k.totv_z, 1)}</b>
                    </span>
                    <span style={{ fontSize: 12, color: zColor(k.putcall_z) }}>
                      mix <b style={S.mono}>{num(k.putcall_z, 1)}</b>
                    </span>
                    {k.flagged && <Pill text="FLAGGED" color={RED} />}
                  </>)}
            </div>
          ))}
        </div>
        <div style={{ ...S.small, marginTop: 10, lineHeight: 1.6 }}>
          <b style={{ color: '#c6cbd8' }}>mix</b> is the put/call volume ratio. It was added after
          2026-08-17, when put and total volume were both correctly quiet and the ratio was at
          +2.7σ — the highest in three months — 90 minutes before the slide.
        </div>
      </div>

      {/* pushes already sent */}
      <div style={S.card}>
        <div style={S.cardTitle}>Alerts sent today</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(d.alerts || []).map((a) => (
            <Pill key={a.key} text={a.label} color={a.fired ? BLUE : DIM} solid={a.fired} />
          ))}
        </div>
        <div style={{ ...S.small, marginTop: 10 }}>
          Solid = pushed to Discord and your phone. Dim = hasn’t fired.
        </div>
      </div>

      {/* honest exclusion */}
      <div style={{ ...S.card, marginBottom: 0 }}>
        <div style={S.cardTitle}>Not shown: dealer gamma</div>
        <p style={{ fontSize: 13, lineHeight: 1.6, color: DIM, margin: 0, maxWidth: '68ch' }}>
          {d.gamma_feed?.reason} Until that feed ticks, a gamma panel here would be a confident
          picture of a stale number — so there isn’t one.
        </p>
      </div>
    </div>
  );
}
