// VacuumMap — where there is dealer structure, and where there is none.
//
// ⛔ THIS IS A MAP, NOT A SIGNAL, AND THE CARD SAYS SO IN ITS OWN TEXT.
// The "shelf with a vacuum below" story was built as a feature and tested three
// separate ways against 837–895 sessions. It failed all three:
//
//   * as a predictor of the next-day drawdown       t = −0.33 (wrong sign)
//   * as a predictor of DEPTH given a fall started  corr +0.057, flat medians
//   * as support — price held above the floor 7.0% of the time against a
//     shuffled null of 5.9% [4.4–7.4]. p = 0.103. It blows through 93% of days.
//
// As a binary it fires on 351 of 725 sessions — 48% of all days — and moves the
// down-tail from 10.6% to 11.4%.
//
// So why render it at all? Because "where is there no dealer positioning" is a
// true structural fact and this is the structure page. Knowing the next real
// strike is 765 is worth the same as knowing where the put wall is: it frames
// what you are looking at. It is NOT worth sizing on, and a card that showed
// the map without the verdict would invite exactly that — which is how a
// reader ended up asking whether a vacuum meant a fall was coming.
import { useMemo } from 'react';

const AMBER = '#fbbf24', DIM = '#8b93a7', GREEN = '#34d399', RED = '#f87171';

// A strike counts as "real structure" at 25% of the largest concentration on
// the board.
//
// 🚨 THE THRESHOLD IS EXPIRATION-DEPENDENT AND 10% WAS WRONG HERE. The research
// used a dte 1-90 aggregate, where structure spreads across strikes. This page
// plots a NEXT-DAY profile, where gamma piles up at the money - so at a 10% cut
// 21 of 51 strikes qualified, the nearest one was 0.11% away, and the "gap"
// was pure noise floor. At 25% only the real walls survive and the gap becomes
// a fact about the board instead of an artefact of the cut.
const MATERIAL = 0.25;

const bn = (x) => {
  const a = Math.abs(x);
  if (a >= 1e9) return `${x < 0 ? '−' : ''}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${x < 0 ? '−' : ''}$${(a / 1e6).toFixed(0)}M`;
  return `${x < 0 ? '−' : ''}$${a.toFixed(0)}`;
};

function Side({ label, gap, strike, gex, spot, tone }) {
  return (
    <div style={{
      flex: '1 1 190px', minWidth: 0, padding: '9px 11px', borderRadius: 8,
      background: '#0e1220', border: `1px solid ${tone}33`,
    }}>
      <div style={{ fontSize: 10, color: DIM, letterSpacing: '.05em', textTransform: 'uppercase' }}>
        {label}
      </div>
      {strike == null ? (
        <div style={{ fontSize: 13, color: '#e6e9f0', marginTop: 2 }}>
          none in the visible chain
        </div>
      ) : (
        <>
          <div style={{
            fontSize: 15, fontWeight: 700, color: tone,
            fontFamily: 'ui-monospace, Menlo, monospace', fontVariantNumeric: 'tabular-nums',
          }}>
            ${strike.toFixed(0)}
          </div>
          <div style={{ fontSize: 11, color: DIM, marginTop: 2, lineHeight: 1.45 }}>
            {gap.toFixed(2)}% away (${Math.abs(spot - strike).toFixed(2)}) · carries {bn(gex)}
          </div>
        </>
      )}
    </div>
  );
}

export default function VacuumMap({ strikes, spot }) {
  const v = useMemo(() => {
    if (!Array.isArray(strikes) || !strikes.length || !spot) return null;
    const rows = strikes
      .filter((r) => r && r.strike != null && r.net_gamma != null)
      .map((r) => ({ k: Number(r.strike), g: Number(r.net_gamma) }))
      .filter((r) => Number.isFinite(r.k) && Number.isFinite(r.g));
    if (rows.length < 8) return null;
    const peak = Math.max(...rows.map((r) => Math.abs(r.g)));
    if (!(peak > 0)) return null;
    const cut = MATERIAL * peak;

    const below = rows.filter((r) => r.k < spot && Math.abs(r.g) >= cut)
      .sort((a, b) => b.k - a.k)[0] || null;
    const above = rows.filter((r) => r.k > spot && Math.abs(r.g) >= cut)
      .sort((a, b) => a.k - b.k)[0] || null;
    // What you are standing on: the nearest material strike either way.
    const onIt = rows.filter((r) => Math.abs(r.k - spot) <= 1 && Math.abs(r.g) >= cut)
      .sort((a, b) => Math.abs(b.g) - Math.abs(a.g))[0] || null;

    // How empty the space under you is, relative to the whole band.
    const tot = rows.reduce((s, r) => s + Math.abs(r.g), 0);
    const near = rows.filter((r) => r.k < spot && r.k >= spot * 0.99)
      .reduce((s, r) => s + Math.abs(r.g), 0);
    // The genuinely useful numbers on a next-day board: the single biggest
    // positive concentration (what pins you) and the biggest negative one
    // (where dealers amplify instead of damp).
    const pos = rows.filter((r) => r.g > 0).sort((a, b) => b.g - a.g)[0] || null;
    const neg = rows.filter((r) => r.g < 0).sort((a, b) => a.g - b.g)[0] || null;

    return {
      below, above, onIt, peak, pos, neg,
      downGap: below ? (100 * (spot - below.k)) / spot : null,
      upGap: above ? (100 * (above.k - spot)) / spot : null,
      density: tot > 0 ? near / tot : null,
    };
  }, [strikes, spot]);

  if (!v) return null;

  return (
    <div style={{
      background: '#141824', border: '1px solid #232a3d', borderRadius: 12,
      padding: 14, marginTop: 12,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 700 }}>Where the structure runs out</span>
        <span style={{
          fontSize: 9.5, fontWeight: 700, letterSpacing: '.08em', padding: '2px 7px',
          borderRadius: 999, color: DIM, border: `1px solid ${DIM}55`,
        }}>
          DESCRIPTIVE — NOT A SIGNAL
        </span>
      </div>
      <div style={{ fontSize: 11, color: DIM, margin: '3px 0 10px' }}>
        The nearest strike either side carrying at least {Math.round(MATERIAL * 100)}% of the
        largest concentration on the board. Between spot and those levels there is little
        dealer gamma to slow price down. This is the <b style={{ color: '#c6cbd8' }}>next-day</b>{' '}
        profile — a longer-dated aggregate spreads structure differently.
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Side label="next real structure above" gap={v.upGap} strike={v.above?.k}
              gex={v.above?.g} spot={spot} tone={GREEN} />
        <Side label="next real structure below" gap={v.downGap} strike={v.below?.k}
              gex={v.below?.g} spot={spot} tone={AMBER} />
        <div style={{
          flex: '1 1 190px', minWidth: 0, padding: '9px 11px', borderRadius: 8,
          background: '#0e1220', border: '1px solid #1c2233',
        }}>
          <div style={{ fontSize: 10, color: DIM, letterSpacing: '.05em', textTransform: 'uppercase' }}>
            gamma in the 1% below
          </div>
          <div style={{
            fontSize: 15, fontWeight: 700, color: '#e6e9f0',
            fontFamily: 'ui-monospace, Menlo, monospace',
          }}>
            {v.density == null ? '—' : `${(100 * v.density).toFixed(1)}%`}
          </div>
          <div style={{ fontSize: 11, color: DIM, marginTop: 2, lineHeight: 1.45 }}>
            of all gamma on the board sits in the 1% under spot
            {v.onIt ? ` · sitting on ${bn(v.onIt.g)} at $${v.onIt.k.toFixed(0)}` : ''}
          </div>
        </div>
      </div>

      {(v.pos || v.neg) && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          {v.pos && (
            <div style={{ flex: '1 1 190px', padding: '9px 11px', borderRadius: 8,
                          background: '#0e1220', border: `1px solid ${GREEN}33` }}>
              <div style={{ fontSize: 10, color: DIM, letterSpacing: '.05em', textTransform: 'uppercase' }}>
                biggest positive concentration
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color: GREEN,
                            fontFamily: 'ui-monospace, Menlo, monospace' }}>
                ${v.pos.k.toFixed(0)}
              </div>
              <div style={{ fontSize: 11, color: DIM, marginTop: 2, lineHeight: 1.45 }}>
                {bn(v.pos.g)} · {(100 * (v.pos.k - spot) / spot).toFixed(2)}% away — dealers
                damp moves here
              </div>
            </div>
          )}
          {v.neg && (
            <div style={{ flex: '1 1 190px', padding: '9px 11px', borderRadius: 8,
                          background: '#0e1220', border: `1px solid ${RED}33` }}>
              <div style={{ fontSize: 10, color: DIM, letterSpacing: '.05em', textTransform: 'uppercase' }}>
                biggest negative concentration
              </div>
              <div style={{ fontSize: 15, fontWeight: 700, color: RED,
                            fontFamily: 'ui-monospace, Menlo, monospace' }}>
                ${v.neg.k.toFixed(0)}
              </div>
              <div style={{ fontSize: 11, color: DIM, marginTop: 2, lineHeight: 1.45 }}>
                {bn(v.neg.g)} · {(100 * (v.neg.k - spot) / spot).toFixed(2)}% away — dealers
                amplify moves here
              </div>
            </div>
          )}
        </div>
      )}

      {/* ⛔ The verdict travels WITH the map, permanently. Removing this line
          turns a structural fact back into an implied forecast. */}
      <div style={{ fontSize: 11, color: DIM, marginTop: 10, lineHeight: 1.55 }}>
        <b style={{ color: '#c6cbd8' }}>What this does not tell you.</b> A gap below does not
        make a fall more likely, and it does not say how far one would run. Tested three ways
        on 837–895 sessions: as a drawdown predictor it came out the{' '}
        <b style={{ color: '#c6cbd8' }}>wrong sign</b> (t = −0.33); given a fall had already
        started, its correlation with the depth was <b style={{ color: '#c6cbd8' }}>+0.06</b>;
        and as support, price held above the level below{' '}
        <b style={{ color: RED }}>7.0%</b> of the time against a shuffled null of 5.9%
        (p = 0.10) — it is crossed on 93% of the days it is tested. Read it as a map of where
        the walls are, not as a forecast of where price goes.
      </div>
    </div>
  );
}
