// TapeShape — the base case every other verdict sits on top of.
//
// 🚨 THE PAGES NEVER SAID WHICH WAY THE TAPE LEANS. /risk, /session and
// /squeeze all report DEVIATIONS from a baseline, and not one of them ever
// stated the baseline. So "no edge today" read as "nothing is knowable", when
// the unconditional tape has a real, free directional tilt sitting underneath
// every one of those verdicts.
//
// ⛔ AND IT EXISTS TO KILL A STYLIZED FACT, NOT JUST TO STATE ONE. Equity
// indices are supposed to drift up and CRASH down, and I asserted exactly that
// from memory before checking. Measured on this book's own sample the crash
// half is FALSE for this era: daily skew is POSITIVE (+0.42 on 895 sessions),
// the largest single move is an UP day (+9.25% vs −5.92%), and the 5th/95th
// percentiles are symmetric to within 2%.
//
// That distinction is worth money. "Sell puts because you are overpaid for a
// crash tail" and "sell puts because the tape drifts up" imply different
// sizing, and only the second one is true here. A panel that repeated the
// textbook would have someone sizing for a premium this sample does not pay.
//
// Everything is computed server-side from stored closes and reports n, so a
// thin window is visible rather than implied.
import { TrendingUp } from 'lucide-react';

const GREEN = '#34d399', RED = '#f87171', DIM = '#8b93a7';

const S = {
  card: {
    background: '#141824', border: '1px solid #232a3d', borderRadius: 12,
    padding: 16, marginBottom: 16,
  },
  title: { fontSize: 13, fontWeight: 700, marginBottom: 2 },
  small: { fontSize: 11, color: DIM },
  mono: {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
    fontVariantNumeric: 'tabular-nums',
  },
  cell: {
    flex: '1 1 165px', minWidth: 0, padding: '9px 11px', borderRadius: 8,
    background: '#0e1220', border: '1px solid #1c2233',
  },
};

const pct = (x, d = 1) => (x == null ? '—' : `${(100 * x).toFixed(d)}%`);
const sgn = (x, d = 2) => (x == null ? '—' : `${x >= 0 ? '+' : '−'}${Math.abs(x).toFixed(d)}%`);

function Cell({ label, value, note, color }) {
  return (
    <div style={{ ...S.cell, ...(color ? { borderColor: `${color}44` } : null) }}>
      <div style={S.small}>{label}</div>
      <div style={{ ...S.mono, fontSize: 15, fontWeight: 700, color: color || '#e6e9f0' }}>
        {value}
      </div>
      {note && <div style={{ ...S.small, marginTop: 2, lineHeight: 1.4 }}>{note}</div>}
    </div>
  );
}

export default function TapeShape({ data }) {
  if (!data || data.status === 'unavailable') return null;
  if (data.status === 'thin') {
    return (
      <div style={S.card}>
        <div style={S.title}>The shape of the tape</div>
        <div style={S.small}>
          Not enough stored history yet — {data.n} sessions, needs 120+. Quoting tail
          numbers off a shorter window would be quoting noise.
        </div>
      </div>
    );
  }

  // ⛔ The tail claim is graded, never assumed. Only call the left tail fatter
  // if it measurably is; this sample says it is not.
  const tail = data.tail_ratio;
  const leftFatter = tail != null && tail >= 1.10;
  const symmetric = tail != null && tail > 0.90 && tail < 1.10;

  // ⛔ THE CARD LEADS WITH THE CALL. It used to open with "55.0% of sessions
  // close green" and leave the reader to work out what to do about it. Two
  // standing verdicts come out of these numbers and neither changes day to
  // day, so they are stated as instructions and the statistics sit underneath
  // as their evidence.
  const v = data.vrp;
  const verdicts = [];
  if (data.p_up_day > 0.52 && data.drift_ratio > 1.15) {
    verdicts.push({
      call: 'SELL PUTS, NOT CONDORS',
      why: `The tape drifts up — ${pct(data.p_up_day)} of sessions close green and an ordinary `
         + `up move is ${data.drift_ratio.toFixed(2)}× likelier than the same move down. `
         + `A symmetric structure hands that back on the call side.`,
    });
  }
  if (v && v.pct_inside_1sd > 0.75) {
    verdicts.push({
      call: 'SELL EVERY SESSION — DO NOT TIME IT',
      why: `${pct(v.pct_inside_1sd)} of days finish inside the move options priced, against `
         + `${pct(v.fair_inside)} for a fairly priced market — ${v.edge_pts.toFixed(0)} points of `
         + `overpricing. Realised comes in at ${v.mean_ratio.toFixed(2)}× implied. `
         + `Every filter tested against this has failed out of sample.`,
    });
  }

  return (
    <div style={S.card}>
      {verdicts.length > 0 && (
        <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
          {verdicts.map((x) => (
            <div key={x.call} style={{
              padding: '10px 12px', borderRadius: 8,
              background: `${GREEN}0f`, border: `1px solid ${GREEN}55`,
            }}>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: GREEN, letterSpacing: '.02em' }}>
                {x.call}
              </div>
              <div style={{ fontSize: 12, color: '#c6cbd8', marginTop: 3, lineHeight: 1.5 }}>
                {x.why}
              </div>
            </div>
          ))}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <TrendingUp size={14} color={GREEN} />
        <span style={S.title}>The evidence</span>
        <span style={{ ...S.small, marginLeft: 'auto' }}>
          {data.n} sessions · {data.first} → {data.last}
        </span>
      </div>
      <div style={{ ...S.small, margin: '2px 0 10px' }}>
        Standing calls, not daily ones — these come from the base behaviour of the tape and
        do not change session to session. The numbers below are what they rest on.
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Cell
          label="the tape drifts UP"
          value={pct(data.p_up_day)}
          note={`of sessions close green · mean day ${sgn(data.mean_ret, 3)}`}
          color={GREEN}
        />
        <Cell
          label="ordinary moves lean up"
          value={data.drift_ratio == null ? '—' : `${data.drift_ratio.toFixed(2)}×`}
          note={`a +0.5% day (${pct(data.p_up_50)}) vs a −0.5% day (${pct(data.p_dn_50)})`}
          color={GREEN}
        />
        {v && (
          <Cell
            label="options overprice by"
            value={`${v.mean_ratio.toFixed(2)}×`}
            note={`${pct(v.pct_inside_1sd)} of days finish inside the implied move (fair = ${pct(v.fair_inside)}) · n=${v.n}`}
            color={GREEN}
          />
        )}
        <Cell
          label="big moves"
          value={tail == null ? '—' : `${tail.toFixed(2)}×`}
          note={leftFatter
            ? `left tail is fatter — 5th pct ${sgn(data.p05)} vs 95th ${sgn(data.p95)}`
            : symmetric
              ? `roughly SYMMETRIC — 5th pct ${sgn(data.p05)} vs 95th ${sgn(data.p95)}. No crash premium in this sample.`
              : `right tail is fatter — 95th ${sgn(data.p95)} vs 5th pct ${sgn(data.p05)}`}
          color={leftFatter ? RED : null}
        />
      </div>

      <div style={{ ...S.small, marginTop: 10, lineHeight: 1.55 }}>
        <b style={{ color: '#c6cbd8' }}>What it means for structure.</b> The drift is the
        reliable asymmetry: short puts sit on the side that happens less often, and a
        symmetric condor gives that drift away on the call side.{' '}
        {symmetric && (
          <>
            <b style={{ color: '#c6cbd8' }}>It is not a crash premium.</b> The 5th and 95th
            percentiles sit within {Math.abs(100 * (tail - 1)).toFixed(0)}% of each other
            ({sgn(data.p05)} against {sgn(data.p95)}), and the biggest single move in the
            window was <span style={S.mono}>{sgn(data.best_day)}</span> versus a worst of{' '}
            <span style={S.mono}>{sgn(data.worst_day)}</span>. Size for the drift, not for a
            left tail this window does not show.
            {/* 🚨 SKEW IS SHOWN BUT NEVER LOAD-BEARING. The third moment is
                unstable at these sample sizes - it reads +0.42 over 895
                warehouse sessions and −0.23 over the 289 stored here, on
                overlapping data. The 5th/95th ratio agrees across both windows
                (1.02 vs 1.03), so the copy keys on THAT and skew is reported as
                context only. Keying the sentence on skew's sign would have made
                the panel flip its story with the window length. */}
            {data.skew != null && (
              <> Daily skew is{' '}
                <span style={S.mono}>{(data.skew >= 0 ? '+' : '−') + Math.abs(data.skew).toFixed(2)}</span>,
                which is unstable at this sample size — the percentile spread above is the
                measure to trust.
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
