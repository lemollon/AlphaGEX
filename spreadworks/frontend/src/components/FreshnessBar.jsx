// Freshness — "am I looking at a stale page, or stale data?"
//
// Those are two different questions and the pages answered neither. /risk and
// /squeeze both had every timestamp they needed in their payloads (asof_close,
// captured_at, and squeeze's whole `freshness` block with gamma_date /
// expected_date / stale) and rendered none of it. Unlabelled, not broken —
// the same defect as the GEX profile's LIVE badge.
//
// 🚨 THREE RULES, learned the hard way on /session:
//
//  1. FRESHNESS COMES FROM THE DATA, NEVER THE CLOCK. /session's first version
//     derived LIVE from market hours and sat green over a tape that had
//     stopped 30 minutes earlier. Every state here is computed server-side
//     from stored rows; this component only renders what it is handed.
//
//  2. A PRIOR-CLOSE VERDICT IS NOT STALE. Both pages are regime calls built
//     from the previous session by design. Grading them against "today" would
//     show STALE every morning, and a warning that cries wolf daily is one
//     nobody reads. Staleness is measured against the EXPECTED session.
//
//  3. NAME WHAT IS STALE. These pages blend a prior close, a 10:00 snapshot,
//     a */10 watcher and a manual warehouse ingest. "Stale" alone sends you
//     hunting; "gamma is 1 session behind" tells you what to fix.
//
// The refresh time of the browser tab is deliberately shown apart from the
// data ages, because "I loaded this 4 minutes ago" says nothing about whether
// the numbers underneath it are current.
import { Radio } from 'lucide-react';

const GREEN = '#34d399', RED = '#f87171', AMBER = '#fbbf24', DIM = '#8b93a7';

const S = {
  card: {
    background: '#141824', border: '1px solid #232a3d', borderRadius: 12,
    padding: '12px 14px', marginBottom: 14,
  },
  mono: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontVariantNumeric: 'tabular-nums' },
  small: { fontSize: 11, color: DIM },
};

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

/**
 * @param {string}  state    'CURRENT' | 'STALE' | 'UNKNOWN'
 * @param {string}  detail   one line naming what is stale (or why it's fine)
 * @param {Array}   legs     [{key,label,value,ok,note}] — one row per input
 * @param {Date}    loadedAt when the browser last fetched (NOT data freshness)
 */
export default function FreshnessBar({ state, detail, legs = [], loadedAt }) {
  // ⛔ UNKNOWN must never render green. A page that cannot compute its own
  // freshness has to say so, not imply the data is fine.
  const tone = state === 'CURRENT' ? GREEN : state === 'STALE' ? RED : AMBER;
  const label = state === 'CURRENT' ? 'DATA CURRENT'
    : state === 'STALE' ? 'STALE DATA' : 'FRESHNESS UNKNOWN';

  return (
    <div style={{ ...S.card, borderColor: `${tone}55`, background: `${tone}0d` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <Radio size={15} color={tone} />
        <Pill text={label} color={tone} solid={state === 'STALE'} />
        {detail && (
          <span style={{ fontSize: 12.5, color: state === 'STALE' ? '#e6e9f0' : DIM }}>
            {detail}
          </span>
        )}
        {loadedAt && (
          <span style={{ ...S.small, ...S.mono, marginLeft: 'auto' }}>
            page loaded {loadedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      {legs.length > 0 && (
        <div style={{
          display: 'grid', gap: 6, marginTop: 10,
          gridTemplateColumns: 'repeat(auto-fit,minmax(215px,1fr))',
        }}>
          {legs.map((l) => {
            const c = l.ok === false ? RED : l.ok === true ? DIM : AMBER;
            return (
              <div key={l.key} style={{
                padding: '7px 10px', borderRadius: 8, background: '#0e1220',
                border: `1px solid ${l.ok === false ? `${RED}44` : '#1c2233'}`,
              }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                  <span style={{ ...S.small, color: '#c6cbd8' }}>{l.label}</span>
                  {l.value && (
                    <span style={{ ...S.mono, fontSize: 12, marginLeft: 'auto' }}>{l.value}</span>
                  )}
                </div>
                <div style={{ ...S.small, color: c, marginTop: 2 }}>{l.note}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Squeeze's `freshness` block -> the shape above.
 *
 * 🚨 Kept separate from the risk mapping on purpose. Squeeze's data arrives by
 * a MANUAL warehouse ingest, so "gamma is 1 session behind" is a routine and
 * expensive failure here — a stale reading dated as today has already cost a
 * real signal flip. It also distinguishes rows written by the 15:05 capture
 * from rows auto-seeded off the committed CSV, because a page implying a live
 * capture that has never run is claiming a liveness it does not have.
 */
export function squeezeLegs(f) {
  if (!f) return { state: 'UNKNOWN', detail: 'no freshness block in the payload', legs: [] };
  const legs = [];
  const behind = (n) => (n == null ? 'unknown'
    : n <= 0 ? 'current for this session'
    : `${n} session${n === 1 ? '' : 's'} behind`);

  legs.push({
    key: 'gamma', label: 'gamma / GEX', value: f.gamma_date,
    ok: f.gamma_stale_sessions != null ? f.gamma_stale_sessions <= 0 : null,
    note: `${behind(f.gamma_stale_sessions)}${f.expected_date ? ` · expected ${f.expected_date}` : ''}`,
  });
  legs.push({
    key: 'vix', label: 'VIX', value: f.vix_date,
    ok: f.vix_stale_sessions != null ? f.vix_stale_sessions <= 0 : null,
    note: behind(f.vix_stale_sessions),
  });
  if (f.legs_mismatch != null) {
    // 🚨 VIX RUNNING AHEAD OF GAMMA IS THE NORMAL INTRADAY STATE, NOT A FAULT.
    // The VIX row for today lands early; the gamma capture runs at 15:05. So
    // legs_mismatch is true every single day between those two moments. The
    // first version of this bar graded any mismatch as a failure, which would
    // have painted the page STALE mid-session every day — the exact cry-wolf
    // failure this component was written to avoid, shipped inside the fix for
    // it. Caught on the live payload within minutes of deploying.
    //
    // The mismatch only matters when GAMMA — the leg the verdict is built
    // from — is actually behind where it should be. That is already what
    // gamma_stale_sessions says, so this leg reports and never overrules it.
    const vixAhead = f.vix_date && f.gamma_date && f.vix_date > f.gamma_date;
    const gammaBehind = f.gamma_stale_sessions != null && f.gamma_stale_sessions > 0;
    legs.push({
      key: 'agree', label: 'gamma vs VIX dating', value: null,
      ok: !f.legs_mismatch ? true : gammaBehind ? false : null,
      note: !f.legs_mismatch ? 'same session'
        : gammaBehind ? 'DIFFERENT SESSIONS — verdict blends two days'
        : vixAhead ? "VIX already has today's row; gamma captures at 15:05 CT — normal"
        : 'dated apart, but gamma is current for this verdict',
    });
  }
  if (f.captured_sessions != null) {
    legs.push({
      key: 'provenance', label: 'source of the latest row',
      value: f.captured_sessions === 0 ? 'CSV seed' : `${f.captured_sessions} captured`,
      ok: f.latest_is_capture == null ? null : f.latest_is_capture,
      note: f.captured_sessions === 0
        ? 'the 15:05 capture has NEVER run — every row is the committed baseline'
        : f.latest_is_capture ? 'newest row came from the live 15:05 capture'
        : 'newest row came from the CSV seed, not a live capture',
    });
  }
  if (f.window_complete != null) {
    const miss = (f.window_missing || []).length;
    legs.push({
      key: 'window', label: 'percentile window',
      value: f.window_sessions != null ? `${f.window_sessions}/${f.window_needed}` : null,
      ok: !!f.window_complete,
      // A hole in the window silently distorts every percentile on the page.
      note: f.window_complete ? 'complete'
        : miss ? `${miss} session${miss === 1 ? '' : 's'} missing — percentiles are distorted`
        : 'short of a full window',
    });
  }

  const bad = legs.filter((l) => l.ok === false);
  const unknown = legs.filter((l) => l.ok == null);
  return {
    // Only a genuinely failing leg turns the bar red. An informational leg
    // (ok == null) must never be able to do it on its own.
    state: bad.length ? 'STALE' : unknown.length === legs.length ? 'UNKNOWN' : 'CURRENT',
    detail: bad.length
      ? bad.map((l) => `${l.label}: ${l.note}`).join('; ')
      : 'gamma and VIX are both current for the session this verdict is built from',
    legs,
  };
}
