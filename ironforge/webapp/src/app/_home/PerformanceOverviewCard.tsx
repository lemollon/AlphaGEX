/**
 * Hero "Performance Overview" — the approved mock's top-right card.
 *
 * ── THIS IS A DRAWING, NOT A LEDGER ──────────────────────────────────────────
 *
 * Leron's call, 2026-08-27: the hero card is a design element, not a reporting
 * surface. It no longer reads `/api/public/track-record`; nothing here fetches,
 * so the homepage stays fully static and cannot be made ugly by a short record.
 *
 * That reverses the 2026-08-25 decision ("it does need real numbers") which had
 * itself reversed a static drawing shipped hours earlier. Two flips. Before
 * flipping it a third time, read the paragraph below — the reason the real-data
 * version kept coming back is the reason this one carries a label.
 *
 * ── WHY THE "ILLUSTRATIVE" LABEL IS NOT OPTIONAL ─────────────────────────────
 *
 * The figures drawn here (+18.74% / 128 trades / 74% win rate) are the original
 * template's placeholders. No IronForge account has produced them. Published
 * bare on the homepage of a real-money trading product they are a fabricated
 * performance claim — the exact thing the SPARK/FLAME risk-ladder copy and the
 * comparison table were both rewritten to stop doing (see marketing.tsx).
 *
 * The badge and the footnote are what make this a labelled hypothetical instead.
 * Keep the drawing, keep the label. If a future change deletes the label to
 * "match the mock exactly", it is not a styling tweak — it is turning a design
 * illustration into an advertised return.
 *
 * Real, sourced numbers live on /performance and in the public track record.
 */

/** Chart domain. Gridlines and their labels are both derived from it, so a
 *  label can never drift off its own line. */
const MIN = -10
const MAX = 24
const GRID = [20, 10, 0, -10]

/** Hand-authored illustrative curve — the mock's rising, jagged line. */
const SERIES = [
  -5.5, -4.3, -3.5, -1.6, -2.8, -0.8, 0.3, -1.0, 0.0, 1.5,
  -0.2, 1.8, 3.4, 1.9, 2.7, 3.8, 5.3, 6.3, 7.5, 6.1,
  6.9, 8.4, 9.5, 8.0, 9.5, 11.1, 9.5, 8.3, 9.6, 11.7,
  12.9, 14.0, 12.3, 13.2, 14.4, 15.7, 14.1, 13.0, 14.0, 15.2,
  14.4, 13.0, 15.0, 15.9, 14.8, 13.7, 15.2, 16.5, 18.4, 20.4,
  21.8, 21.0,
]

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY']

const TILES = [
  { label: 'Total Return', value: '+18.74%', green: true },
  { label: 'Trades Executed', value: '128', green: false },
  { label: 'Win Rate', value: '74%', green: false },
]

/** Fraction of the plot height, measured from the top, for a value. */
function yFrac(v: number): number {
  return (MAX - v) / (MAX - MIN)
}

function Chart() {
  const W = 300
  const H = 100
  const coords = SERIES.map(
    (p, i) => `${(i / (SERIES.length - 1)) * W},${yFrac(p) * H}`,
  ).join(' ')

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-[150px] w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label="Illustrative rising performance curve. Not actual trading results."
    >
      <defs>
        <linearGradient id="hero-perf-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#22C55E" stopOpacity="0.34" />
          <stop offset="100%" stopColor="#22C55E" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {GRID.map((v) => (
        <line
          key={v}
          x1="0"
          y1={yFrac(v) * H}
          x2={W}
          y2={yFrac(v) * H}
          stroke="#242424"
          strokeWidth="0.6"
        />
      ))}
      <polygon points={`0,${H} ${coords} ${W},${H}`} fill="url(#hero-perf-fill)" />
      <polyline
        points={coords}
        fill="none"
        stroke="#22C55E"
        strokeWidth="1.7"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

export default function PerformanceOverviewCard() {
  return (
    <div className="rounded-2xl border border-[#2B2B2B] bg-[#141414]/80 p-5 shadow-[0_12px_32px_rgba(0,0,0,.28)]">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[15px] text-gray-200">Performance Overview</div>
        <span className="rounded-full border border-[#3A3A3A] bg-[#0E0F0F] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[#B8B8B8]">
          Illustrative
        </span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2.5">
        {TILES.map(({ label, value, green }) => (
          <div key={label} className="rounded-lg border border-[#2B2B2B] bg-[#0E0F0F] px-3 py-2.5">
            <div className="text-[11px] leading-tight text-[#B8B8B8]">{label}</div>
            <div
              className={`mt-1 text-[19px] font-bold tabular-nums ${green ? 'text-[#22C55E]' : 'text-white'}`}
            >
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Value axis sits outside the SVG: the plot is drawn with
          preserveAspectRatio="none" so any text inside it would stretch. Both
          columns share MIN/MAX, so the labels stay welded to their gridlines. */}
      <div className="mt-4 flex gap-2">
        <div className="relative w-8 shrink-0 h-[150px]">
          {GRID.map((v) => (
            <span
              key={v}
              className="absolute right-0 -translate-y-1/2 text-[10px] tabular-nums text-[#7C7772]"
              style={{ top: `${yFrac(v) * 100}%` }}
            >
              {v}%
            </span>
          ))}
        </div>
        <div className="min-w-0 flex-1">
          <Chart />
          <div className="mt-1.5 flex justify-between px-0.5 text-[10px] tracking-wide text-[#7C7772]">
            {MONTHS.map((m) => (
              <span key={m}>{m}</span>
            ))}
          </div>
        </div>
      </div>

      <p className="mt-3 border-t border-[#1E1E1E] pt-3 text-[11px] leading-relaxed text-[#B8B8B8]">
        Illustrative example shown for design purposes. Not actual trading results. Past
        performance does not indicate future results.
      </p>
    </div>
  )
}
