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
import CallHistory from '../components/CallHistory';

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
// Mirrors routes_risk.CONFIRM_ARM_Z. Kept as one constant so the wording, the
// dot colour and the chart's ARMS gridline can never drift apart.
const CONFIRM_ARM_Z = 1.5;
const num = (x, d = 2) => (x == null || Number.isNaN(x) ? '—' : Number(x).toFixed(d));

// z-score -> colour. Only ±2 is a threshold anywhere in this system; 1.5 arms
// the confirmation watcher. Anything below reads as ordinary and must not be
// coloured like a signal.
function zColor(z) {
  if (z == null) return DIM;
  if (z > 2) return RED;
  if (z > CONFIRM_ARM_Z) return AMBER;
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

// A chart header that states the CURRENT READING, its age, and what the
// reading means — not just the window the chart covers.
//
// 🚨 Both charts previously headed themselves with a RANGE ("to 11:50 CT",
// "08:31–14:59 CT · rolling z vs the trailing 63"). That is the span the
// chart draws, which is a different question from "what does it say right
// now, and is that number still current". You could read the shape and still
// not know the level.
//
// 🚨 The two charts carry DIFFERENT ages on purpose. Spot is written by the
// confirmation watcher and the z-scores by the rolling watcher; they poll on
// the same */10 cron but either can miss a slot. One shared "last reading"
// caption would quietly attribute one watcher's freshness to the other.
function Readout({ value, unit, meaning, meaningColor, at, ageMin, valueColor }) {
  const stale = ageMin != null && ageMin > 15;
  return (
    <div style={{ marginLeft: 'auto', textAlign: 'right', lineHeight: 1.25 }}>
      <div>
        <span style={{ ...S.mono, fontSize: 19, fontWeight: 700, color: valueColor || '#e6e9f0' }}>
          {value}
        </span>
        {unit && <span style={{ ...S.small, marginLeft: 3 }}>{unit}</span>}
        {meaning && (
          <span style={{ fontSize: 11.5, fontWeight: 700, color: meaningColor || DIM,
                         marginLeft: 8, letterSpacing: '.03em' }}>{meaning}</span>
        )}
      </div>
      <div style={{ ...S.small, ...S.mono, color: stale ? AMBER : DIM }}>
        {at ? `${at} CT${ageMin != null ? ` · ${ageMin}m ago` : ''}` : 'no reading yet'}
        {stale ? ' · STALLED' : ''}
      </div>
    </div>
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
        {/* 🚨 THE CHART DREW A SHAPE AND NEVER SAID WHAT IT READS. The axis
            labelled the triggers and the reference, but the one number you
            actually want — where SPY IS — existed only as an unlabelled dot.
            Label it on the line, and again in the header. */}
        <circle cx={X(last.minute_ct)} cy={Y(last.spot)} r="4" fill="#e6e9f0" />
        <text x={Math.min(X(last.minute_ct) + 8, W - mr - 44)} y={Y(last.spot) + 4}
              fill="#e6e9f0" style={{ fontSize: 12, fontWeight: 700, ...S.mono }}>
          {num(last.spot)}
        </text>
        <text x={ml} y={H - 8} fill={DIM} style={{ fontSize: 10, ...S.mono }}>{ctLabel(m0)}</text>
        <text x={W - mr} y={H - 8} textAnchor="end" fill={DIM}
              style={{ fontSize: 10, ...S.mono }}>{ctLabel(m1)} CT</text>
      </svg>
    </div>
  );
}

// ── The flow track. The tape above answers "where is price"; this answers
// "what is the option flow doing while it gets there", and until 2026-08-19
// the rolling watcher only wrote the two LEVEL z-scores — the exact pair that
// were both quiet on 08-17 while the MIX was the outlier of the trailing 63.
// The mix is drawn solid because it is the leg the arming decision is made on;
// put/total are drawn faint because they are context, not the signal.
//
// 🚨 Gaps are NOT bridged. A missing slot means a poll failed, and a line
// drawn straight through it would invent a reading that was never taken.
function FlowTrack({ tape }) {
  const rows = (tape || []).filter((r) => r.roll_pc_z != null || r.roll_putv_z != null);
  if (rows.length < 2) {
    return <div style={{ ...S.small, padding: '18px 0', textAlign: 'center' }}>
      The rolling flow watcher hasn’t written two readings yet today.
    </div>;
  }
  const W = 900, H = 150, ml = 52, mr = 14, mt = 12, mb = 22;
  const iw = W - ml - mr, ih = H - mt - mb;
  const zs = rows.flatMap((r) => [r.roll_pc_z, r.roll_putv_z, r.roll_totv_z]).filter((z) => z != null);
  const lo = Math.min(-1, ...zs) - 0.4, hi = Math.max(2.4, ...zs) + 0.4;
  const m0 = rows[0].minute_ct, m1 = rows[rows.length - 1].minute_ct;
  const X = (m) => ml + (m1 === m0 ? iw / 2 : ((m - m0) / (m1 - m0)) * iw);
  const Y = (v) => mt + ((hi - v) / (hi - lo)) * ih;
  // segment on nulls rather than skipping over them
  const paths = (key) => {
    const out = []; let cur = [];
    rows.forEach((r) => {
      if (r[key] == null) { if (cur.length > 1) out.push(cur); cur = []; return; }
      cur.push(`${cur.length ? 'L' : 'M'}${X(r.minute_ct).toFixed(1)} ${Y(r[key]).toFixed(1)}`);
    });
    if (cur.length > 1) out.push(cur);
    return out.map((seg) => seg.join(' '));
  };
  const gridline = (v, color, label, dash) => (
    <g key={label}>
      <line x1={ml} y1={Y(v)} x2={W - mr} y2={Y(v)} stroke={color} strokeWidth="1"
            strokeDasharray={dash} opacity=".55" />
      <text x={ml - 7} y={Y(v) + 3.5} textAnchor="end" fill={color}
            style={{ fontSize: 10, ...S.mono }}>{v.toFixed(1)}σ</text>
      <text x={W - mr} y={Y(v) - 4} textAnchor="end" fill={color}
            style={{ fontSize: 9, fontWeight: 700, letterSpacing: '.08em' }}>{label}</text>
    </g>
  );
  const last = [...rows].reverse().find((r) => r.roll_pc_z != null);
  const lastAny = [...rows].reverse().find((r) => r.roll_putv_z != null);
  return (
    <div style={{ overflowX: 'auto', minWidth: 0 }}>
      <svg width={W} height={H} role="img"
           aria-label="Rolling option-flow z-scores through the session: the put/call mix, plus put and total volume">
        {gridline(2, RED, 'SPIKE', '4 3')}
        {gridline(1.5, AMBER, 'ARMS', '2 4')}
        {gridline(0, DIM, '', '1 5')}
        {paths('roll_totv_z').map((d, i) => <path key={`t${i}`} d={d} fill="none" stroke={DIM} strokeWidth="1" opacity=".45" />)}
        {paths('roll_putv_z').map((d, i) => <path key={`p${i}`} d={d} fill="none" stroke={BLUE} strokeWidth="1" opacity=".5" />)}
        {paths('roll_pc_z').map((d, i) => <path key={`c${i}`} d={d} fill="none" stroke="#e6e9f0" strokeWidth="1.9" strokeLinejoin="round" />)}
        {last && (<>
          <circle cx={X(last.minute_ct)} cy={Y(last.roll_pc_z)} r="4"
                  fill={zColor(last.roll_pc_z) === DIM ? '#e6e9f0' : zColor(last.roll_pc_z)} />
          <text x={Math.min(X(last.minute_ct) + 8, W - mr - 40)} y={Y(last.roll_pc_z) + 4}
                fill={zColor(last.roll_pc_z) === DIM ? '#e6e9f0' : zColor(last.roll_pc_z)}
                style={{ fontSize: 12, fontWeight: 700, ...S.mono }}>
            {num(last.roll_pc_z, 2)}σ
          </text>
        </>)}
        <text x={ml} y={H - 6} fill={DIM} style={{ fontSize: 10, ...S.mono }}>{ctLabel(m0)}</text>
        <text x={W - mr} y={H - 6} textAnchor="end" fill={DIM}
              style={{ fontSize: 10, ...S.mono }}>{ctLabel(m1)} CT</text>
      </svg>
      {/* The legend named the lines and never gave their values. A reader
          could see three wiggles and still not know what the flow is. */}
      <div style={{ ...S.small, display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 6 }}>
        <span><b style={{ color: '#e6e9f0' }}>——</b> mix (put/call ratio){' '}
          <b style={{ ...S.mono, color: zColor(last?.roll_pc_z) === DIM ? '#e6e9f0' : zColor(last?.roll_pc_z) }}>
            {num(last?.roll_pc_z, 2)}σ
          </b>
        </span>
        <span style={{ color: BLUE }}>—— put volume{' '}
          <b style={S.mono}>{num(lastAny?.roll_putv_z, 2)}σ</b>
        </span>
        <span>—— total volume <b style={S.mono}>{num(lastAny?.roll_totv_z, 2)}σ</b></span>
      </div>
    </div>
  );
}

// Supporting detail collapses. The page's job is to answer in the first
// screen; the clocks and the alert log are proof, and proof does not need to
// be open by default. (Same restructure that took the squeeze page from 6.3
// screens to 3.)
function Fold({ title, meta, children, open: init = false }) {
  const [open, setOpen] = useState(init);
  return (
    <div style={S.card}>
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        style={{ all: 'unset', cursor: 'pointer', display: 'flex', alignItems: 'center',
                 gap: 10, width: '100%', boxSizing: 'border-box' }}>
        <span style={{ color: DIM, fontSize: 11, width: 10 }}>{open ? '▾' : '▸'}</span>
        <span style={S.cardTitle}>{title}</span>
        {meta && <span style={{ ...S.small, marginLeft: 'auto' }}>{meta}</span>}
      </button>
      {open && <div style={{ marginTop: 12 }}>{children}</div>}
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

  if (err) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Couldn’t load the session: {err}</div></div></div>;
  if (!d) return <div className="flex-1 overflow-y-auto"><div style={S.wrap}><div style={S.card}>Loading…</div></div></div>;

  const c = d.confirm || {};

  // ── CURRENT READINGS, per chart, each on its own clock.
  // 🚨 Spot and the z-scores are written by two different watchers into the
  // same 10-minute slot. Either can miss one, so the newest row WITH A SPOT is
  // not necessarily the newest row with a mix — reading both off d.clock would
  // report one watcher's freshness under the other's chart.
  const tapeRows = d.tape || [];
  // 🚨 PARSE THE SERVER'S OWN CT CLOCK OUT OF THE STRING — never new Date().
  // `asof` is "...T12:03:21-05:00". new Date(asof).getHours() converts to the
  // BROWSER's timezone, so this page viewed from anywhere but Central would
  // have reported ages hours off and shown a fresh tape as STALLED (or worse,
  // a stalled one as fresh). Reading the browser clock instead of the payload
  // is the same defect as the old LIVE badge, and the same trap that made
  // Git Bash print 13:57 for an 08:57 CT session.
  const nowMin = (() => {
    const m = /T(\d{2}):(\d{2})/.exec(d.asof || '');
    return m ? (+m[1]) * 60 + (+m[2]) : null;
  })();
  const spotRow = [...tapeRows].reverse().find((r) => r.spot != null) || null;
  const mixRow = [...tapeRows].reverse().find((r) => r.roll_pc_z != null) || null;
  const spotNow = spotRow?.spot ?? null;
  const mixNow = mixRow?.roll_pc_z ?? null;
  const ageOf = (row) => (row && nowMin != null ? Math.max(0, nowMin - row.minute_ct) : null);
  const spotAge = ageOf(spotRow), mixAge = ageOf(mixRow);

  // What the mix number MEANS. A bare sigma is only readable if you already
  // hold the thresholds in your head; these are the same cuts the watcher and
  // the chart's gridlines use, so the word can never disagree with the line.
  const mixMeaning = mixNow == null ? null
    : mixNow > 2 ? 'SPIKE'
    : mixNow > CONFIRM_ARM_Z ? 'ELEVATED — would arm'
    : mixNow > 1 ? 'slightly heavy'
    : mixNow < -1 ? 'call-heavy'
    : 'ordinary';
  const live = d.clock?.live;
  const fired = !!c.fired_dir;
  const dirColor = c.fired_dir === 'DOWN' ? RED : GREEN;
  // STALLED/NO DATA are faults and must read red; a closed watch window is
  // normal and reads neutral. Only a genuinely fresh tape is green.
  const st = d.clock?.state;
  const clockTone = live ? GREEN : (st === 'STALLED' || st === 'NO DATA') ? RED : DIM;

  // The headline. Priority order matters: a FIRED call outranks everything,
  // then armed-and-waiting, then the quiet state. Never lead with the quiet
  // state while a call is live on the same page.
  // Magnitude, in the units the decision is made in. A hit rate alone doesn't
  // say whether there is anything left to trade at 11:20 CT.
  const rw = d.runway?.armed, rwBase = d.runway?.base;
  const px = d.to_trigger?.spot || c.ref_spot;
  const dollars = (pct) => (pct == null || !px ? null : (pct / 100) * px);
  const rsf = d.run_since_fire;
  const leftPct = (rw?.median_win != null && rsf?.pct != null) ? rw.median_win - rsf.pct : null;

  let head, headColor, headBody;
  if (fired) {
    head = `${c.fired_dir} CONFIRMED`;
    headColor = dirColor;
    headBody = `Broke through ${num(c.fired_dir === 'DOWN' ? d.levels?.down : d.levels?.up)} at a session ${c.fired_dir === 'DOWN' ? 'low' : 'high'} from a ${num(c.ref_spot)} reference. `
      + (rsf ? `It has run **$${num(Math.abs(rsf.dollars))}** since. ` : '')
      + (rw ? `On flagged days a break like this continues ${(rw.continued * 100).toFixed(0)}% of the time and, when it does, the median run from here to the close is ${num(rw.median_win, 2)}%${dollars(rw.median_win) ? ` ≈ $${num(dollars(rw.median_win))}` : ''}`
            + (leftPct != null ? ` — about **$${num(Math.max(0, dollars(leftPct)))} of that is still ahead**. ` : '. ')
            + `When it fails it gives back a median ${num(Math.abs(rw.median_loss), 2)}%. `
          : 'On flagged days that break keeps going 63% of the time vs a 50% coin flip. ')
      + `**Reduce or close any short ${c.fired_dir === 'DOWN' ? 'put' : 'call'} premium — don't add.**`;
  } else if (c.armed) {
    head = 'ARMED — WAITING FOR A SIDE';
    headColor = AMBER;
    headBody = `This morning's put/call mix was ${num(c.putcall_z, 1)}σ — unusual enough that a bigger-than-normal move is likely, but the direction is a coin flip until price commits. Watching for a break through ${num(d.levels?.down)} or ${num(d.levels?.up)}. `
      + (rw ? `If one comes, the median run from the break to the close on days like this is ${num(rw.median, 2)}%${dollars(rw.median) ? ` ≈ $${num(dollars(rw.median))} of SPY` : ''}, against ${num(rwBase?.median ?? 0, 2)}% on an unflagged break.` : '');
  } else if (c.armed === false) {
    head = 'NOT ARMED';
    headColor = DIM;
    headBody = `Morning flow mix was ordinary (${num(c.putcall_z, 1)}σ). A price break today carries no more information than a coin flip, so this page will stay quiet whatever SPY does.`;
  } else {
    head = 'WAITING FOR THE 10:00 SNAPSHOT';
    headColor = DIM;
    headBody = 'The morning flow reading is captured between 10:00 and 10:35 CT. Nothing here can arm before then.';
  }

  // 🚨 THE SCROLL CONTAINER IS NOT OPTIONAL. App.jsx's shell is
  // `h-dvh ... overflow-hidden`, so a route that does not bring its own
  // scroller is CLIPPED AT THE VIEWPORT — content below the fold cannot be
  // reached and there is no scrollbar to hint that it exists. Every other
  // routed page carries this. /session shipped without it and happened to fit
  // on one screen, so nothing showed; the flow track, the calibration
  // scorecard and the history fold then pushed the bottom off the page.
  return (
    <div className="flex-1 overflow-y-auto">
    <div style={S.wrap}>
      <h1 style={S.h1}>Session</h1>
      <p style={S.sub}>
        What is happening right now. The regime call lives on Risk and Squeeze — this is the tape.
      </p>

      {/* Freshness. 🚨 Derived from the newest TAPE ROW, never from market
          hours — the first version called itself LIVE from 08:30-15:00 while
          the watchers only run 10:10-14:00, so it sat green over a tape that
          had stopped half an hour earlier. */}
      <div style={{
        ...S.card, display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
        borderColor: `${clockTone}55`, background: `${clockTone}0d`, marginBottom: 12,
      }}>
        <Radio size={15} color={clockTone} />
        <Pill text={d.clock?.state} color={clockTone} solid={live} />
        {d.clock?.last_reading_ct && (
          <span style={{ ...S.mono, fontSize: 12.5, color: clockTone, fontWeight: 700 }}>
            last reading {d.clock.last_reading_ct} CT
            {d.clock.age_min != null && ` · ${d.clock.age_min}m ago`}
          </span>
        )}
        <span style={{ ...S.small, marginLeft: 'auto' }}>
          {/* A countdown, not just a window. "closes in 47m" is the difference
              between waiting for a break and knowing there is no time left
              for one. */}
          {d.window?.closes_in_min > 0 && live
            ? `watch window closes ${d.window.close_ct} CT · ${d.window.closes_in_min}m left · refreshes every 30s`
            : d.window?.opens_in_min > 0
              ? `watch window opens ${d.window.open_ct} CT · ${d.window.opens_in_min}m away`
              : d.clock?.detail || `watch window ${d.clock?.window_ct || '10:10–14:00'} CT · page refreshes every 30s`}
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
        <p style={{ fontSize: 14.5, lineHeight: 1.6, color: '#c6cbd8', margin: 0, maxWidth: '66ch' }}>
          {headBody.split('**').map((t, i) => i % 2
            ? <b key={i} style={{ color: '#e6e9f0' }}>{t}</b> : <span key={i}>{t}</span>)}
        </p>
        {/* 🚨 This used to state that a DOWN call opposes EBB and an UP call
            doesn't. That is EBB's usual shape, not a fact this page checked —
            and a position claim nobody verified is exactly the kind of thing
            that reads as confirmation at 11:20 CT. It now says what it knows. */}
        <p style={{ ...S.small, margin: '9px 0 0' }}>
          Advisory — this page moves nothing, and no bot reads it. {fired
            ? `A ${c.fired_dir} call matters to a short ${c.fired_dir === 'DOWN' ? 'put' : 'call'} position; check Positions for today's actual side.`
            : ''}
        </p>
      </div>

      {/* the tape */}
      <div style={S.card}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
          <span style={{ ...S.cardTitle, marginBottom: 0 }}>SPY since the 10:00 CT reference</span>
          <Readout
            value={spotNow != null ? num(spotNow) : '—'}
            meaning={spotNow != null && c.ref_spot
              ? `${spotNow - c.ref_spot >= 0 ? '+' : ''}${num(spotNow - c.ref_spot)} vs 10:00`
              : null}
            meaningColor={spotNow != null && c.ref_spot
              ? (spotNow >= c.ref_spot ? GREEN : RED) : DIM}
            at={spotRow ? ctLabel(spotRow.minute_ct) : null}
            ageMin={spotAge}
          />
        </div>
        <Tape tape={d.tape} levels={d.levels} confirm={c} />

        {/* How far from committing — arithmetic, not pixels. */}
        {!fired && d.to_trigger?.down != null && (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 10 }}>
            {[['DOWN', d.to_trigger.down, d.to_trigger.down_pct, RED],
              ['UP', d.to_trigger.up, d.to_trigger.up_pct, GREEN]].map(([lbl, dist, pct, col]) => (
              <div key={lbl} style={{
                flex: '1 1 200px', padding: '9px 11px', borderRadius: 8,
                background: '#0e1220', border: `1px solid ${col}33`,
              }}>
                <div style={{ ...S.small, color: col, fontWeight: 700, letterSpacing: '.06em' }}>
                  {dist <= 0 ? `THROUGH THE ${lbl} TRIGGER` : `${dist.toFixed(2)} TO THE ${lbl} TRIGGER`}
                </div>
                <div style={{ ...S.mono, fontSize: 12, color: DIM, marginTop: 2 }}>
                  {dist <= 0 ? 'waiting on a session extreme to count it' : `${Math.abs(pct).toFixed(2)}% away`}
                </div>
              </div>
            ))}
          </div>
        )}
        {fired && d.run_since_fire && (
          <div style={{ marginTop: 10, padding: '9px 11px', borderRadius: 8,
                        background: '#0e1220', border: `1px solid ${dirColor}33` }}>
            <span style={{ ...S.small, color: dirColor, fontWeight: 700, letterSpacing: '.06em' }}>
              RUN SINCE THE CONFIRMATION
            </span>
            <span style={{ ...S.mono, fontSize: 13, marginLeft: 10 }}>
              ${num(Math.abs(d.run_since_fire.dollars))} · {num(d.run_since_fire.pct, 2)}%
            </span>
          </div>
        )}

        <div style={{ ...S.small, marginTop: 8 }}>
          Session range since the reference: {num(c.run_min)} – {num(c.run_max)}.
          A break only counts at a session extreme, so a dip that recovers doesn’t arm the rest of the day.
        </div>
      </div>

      {/* the flow track — the second half of the tape, and the half that was
          missing. Price says what happened; this says what the option flow was
          doing while it happened. */}
      <div style={S.card}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
          <span style={{ ...S.cardTitle, marginBottom: 0 }}>Option flow through the session</span>
          <Readout
            value={mixNow != null ? num(mixNow, 2) : '—'} unit="σ mix"
            valueColor={zColor(mixNow) === DIM ? '#e6e9f0' : zColor(mixNow)}
            meaning={mixMeaning} meaningColor={zColor(mixNow)}
            at={mixRow ? ctLabel(mixRow.minute_ct) : null}
            ageMin={mixAge}
          />
        </div>
        <FlowTrack tape={d.tape} />
        <div style={{ ...S.small, marginTop: 8, lineHeight: 1.6, maxWidth: '72ch' }}>
          Covers {d.clock?.tape_window_ct || '08:31–14:59'} CT · each point is graded against the
          trailing 63 sessions <i>at that same minute</i>, so 09:00 is compared with 63 other 09:00s.{' '}
          The <b style={{ color: '#e6e9f0' }}>mix</b> line is the put/call ratio — the leg the arming
          decision is made on, and the one that read +2.7σ on 2026-08-17 while put and total volume
          were both quiet. It was only graded at the three fixed clocks until 2026-08-19; every 10
          minutes is new here. A break in a line is a poll that failed, not a flat reading.
          {' '}The tape records the <b style={{ color: '#c6cbd8' }}>whole session</b>; the flow
          alert still only fires 10:36–14:00 CT, where it was measured. A morning or
          late-afternoon crossing shows up here and deliberately does not push.
        </div>
      </div>

      {/* fixed clocks */}
      <Fold title="Flow clocks"
            meta={`${(d.clocks || []).filter(k => k.captured).length} of ${(d.clocks || []).length} captured${(d.clocks || []).some(k => k.flagged) ? ' · flagged' : ''}`}>
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
          <b style={{ color: '#c6cbd8' }}>mix</b> is the put/call volume ratio. Added after
          2026-08-17, when put and total volume were both correctly quiet and the ratio was at
          +2.7σ — the highest in three months — 90 minutes before the slide.
        </div>
      </Fold>

      {/* IS THE RULE STILL PASSING — the decay monitor had no UI anywhere.
          An advisory surface that can't say whether its own rule still works
          is asking to be trusted on faith, and this repo has already watched
          an edge die in the open. */}
      <Fold title="Is this signal still working?"
            meta={d.calibration?.verdict
              ? `${d.calibration.verdict}${d.calibration.n_armed_fired != null ? ` · ${d.calibration.n_armed_fired} armed firings` : ''}`
              : 'no scorecard'}>
        {d.calibration?.verdict ? (<>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
            <Pill text={d.calibration.verdict}
                  color={d.calibration.verdict === 'PASS' ? GREEN
                       : d.calibration.verdict === 'DISARM' ? RED
                       : d.calibration.verdict === 'WARN' ? AMBER : DIM}
                  solid={d.calibration.verdict === 'DISARM'} />
            <span style={S.small}>
              rolling {d.calibration.window_months}-month window · {d.calibration.sessions} sessions
              {d.calibration.live_sessions ? ` (${d.calibration.live_sessions} live)` : ''}
            </span>
          </div>
          <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit,minmax(190px,1fr))' }}>
            {[['continuation, armed', d.calibration.continuation, true],
              ['same-window base', d.calibration.base_continuation, true],
              ['95% lower bound', d.calibration.continuation_lcb, true],
              ['armed share of sessions', d.calibration.armed_share, true],
              ['stage-1 big-move lift', d.calibration.stage1_lift, false]].map(([lbl, v, pct]) => (
              <div key={lbl} style={{ padding: '9px 11px', borderRadius: 8, background: '#0e1220',
                                      border: '1px solid #1c2233' }}>
                <div style={S.small}>{lbl}</div>
                <div style={{ ...S.mono, fontSize: 16, fontWeight: 700, marginTop: 2 }}>
                  {v == null ? '—' : pct ? `${(v * 100).toFixed(1)}%` : `${v.toFixed(2)}×`}
                </div>
              </div>
            ))}
          </div>
          {(d.calibration.reasons || []).length > 0 && (
            <div style={{ ...S.small, marginTop: 10, lineHeight: 1.6 }}>
              {d.calibration.reasons.join(' · ')}
            </div>
          )}
          {d.runway?.armed && d.runway?.base && (
            <div style={{ ...S.small, marginTop: 12, lineHeight: 1.7, maxWidth: '72ch' }}>
              <b style={{ color: '#c6cbd8' }}>Magnitude, not just hit rate.</b> On an armed day a
              confirmed break runs a median {num(d.runway.armed.median_win, 2)}% when it works and
              gives back {num(Math.abs(d.runway.armed.median_loss), 2)}% when it doesn’t —{' '}
              <b style={{ color: '#e6e9f0' }}>{num(d.runway.payoff_ratio, 1)}:1</b> on n={d.runway.armed.n}.
              An unflagged break is {num(d.runway.base_payoff_ratio, 2)}:1
              ({num(d.runway.base.median_win, 2)}% vs {num(Math.abs(d.runway.base.median_loss), 2)}%),
              which is why the hit rate alone was never the point.
            </div>
          )}
        </>) : (
          <div style={S.small}>The nightly scorer hasn’t written a window yet.</div>
        )}
      </Fold>

      {/* the track record — sessions, not claims */}
      <Fold title="Recent sessions"
            meta={`${(d.history || []).filter(h => h.armed).length} armed of ${(d.history || []).length}`}>
        {(d.history || []).length === 0
          ? <div style={S.small}>No scored sessions yet.</div>
          : (<>
            <div style={{ display: 'grid', gap: 4 }}>
              {d.history.map((h) => (
                <div key={h.d} style={{
                  display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
                  padding: '6px 9px', borderRadius: 7,
                  background: h.armed ? '#0e1220' : 'transparent',
                  border: `1px solid ${h.armed ? '#232a3d' : 'transparent'}`,
                }}>
                  <span style={{ ...S.mono, fontSize: 11.5, color: DIM, width: 82 }}>{h.d}</span>
                  <span style={{ fontSize: 11.5, color: zColor(h.pcz), width: 62 }}>
                    mix <b style={S.mono}>{num(h.pcz, 1)}</b>
                  </span>
                  {h.armed
                    ? <Pill text="ARMED" color={AMBER} />
                    : <span style={{ ...S.small, width: 54 }}>quiet</span>}
                  {h.fired_dir
                    ? <span style={{ fontSize: 11.5, color: h.fired_dir === 'DOWN' ? RED : GREEN }}>
                        {h.fired_dir} break
                      </span>
                    : <span style={S.small}>no break</span>}
                  {h.continued != null && (
                    <span style={{ ...S.small, color: h.continued ? GREEN : RED }}>
                      {h.continued ? 'continued' : 'faded'}
                    </span>
                  )}
                  <span style={{ ...S.mono, fontSize: 11.5, marginLeft: 'auto',
                                 color: (h.move_pct || 0) >= 0 ? GREEN : RED }}>
                    {h.move_pct == null ? '—' : `${h.move_pct >= 0 ? '+' : ''}${num(h.move_pct, 2)}%`}
                  </span>
                </div>
              ))}
            </div>
            <div style={{ ...S.small, marginTop: 10, lineHeight: 1.6 }}>
              Highlighted rows armed on the morning mix. “continued” means the break kept going to
              the close — the outcome the 63% is measured on. The % column is 10:00 CT to the close.
            </div>
          </>)}
      </Fold>

      {/* pushes already sent */}
      <Fold title="Alerts sent today"
            meta={`${(d.alerts || []).filter(a => a.fired).length} sent`}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {(d.alerts || []).map((a) => (
            <Pill key={a.key} text={a.label} color={a.fired ? BLUE : DIM} solid={a.fired} />
          ))}
        </div>
        <div style={{ ...S.small, marginTop: 10 }}>
          Solid = pushed to Discord and your phone. Dim = hasn’t fired.
        </div>
      </Fold>

      {/* honest exclusion */}
      <Fold title="Why there's no gamma panel here">
        <p style={{ fontSize: 13, lineHeight: 1.6, color: DIM, margin: 0, maxWidth: '68ch' }}>
          {d.gamma_feed?.reason} Until that feed ticks, a gamma panel here would be a confident
          picture of a stale number — so there isn’t one. The GEX Profile page carries the map.
        </p>
      </Fold>

      <CallHistory surface="session" title="Session call history" />
    </div>
    </div>
  );
}
