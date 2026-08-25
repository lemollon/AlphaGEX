/**
 * Hero top-right card — a STATIC ILLUSTRATION of the dashboard, not a data view.
 *
 * Leron asked for the mock's chart as an image rather than a live reading. This
 * is that: a fixed drawing, no fetch, no database, no failure state, identical
 * on every load. Inline SVG rather than a PNG because it is ~1KB, stays crisp at
 * any density, needs no asset pipeline, and can be edited in a diff.
 *
 * ── WHY IT CARRIES NO NUMBERS ────────────────────────────────────────────────
 *
 * The approved mock fills this card with "+18.74% · 128 trades · 74% win rate"
 * over a rising line. Those are the original template's placeholder figures. No
 * IronForge account has ever produced them, and they have been removed from this
 * codebase three separate times — from DashboardPreview, then from the card that
 * replaced it, then again when it was rebuilt.
 *
 * A static invented return on the public homepage of a real-money trading
 * product is a fabricated performance claim. It does not become acceptable by
 * being decorative, and it is materially WORSE baked into a picture, because a
 * number in an image cannot be grepped, tested, or noticed in review the way a
 * literal in a component can.
 *
 * So the LAYOUT is the mock's — title row, three stat tiles, rising area chart
 * with month ticks — and the values are drawn as redaction bars. That reads as
 * "this is what the dashboard looks like", which is exactly what it is, and it
 * looks deliberate rather than broken (blanking the tiles to em-dashes was tried
 * before and just looked like a bug).
 *
 * ── THE RULE ─────────────────────────────────────────────────────────────────
 *
 * If a real figure is ever wanted here, it must come from the ledger — see
 * `git log` for PerformanceOverviewCard, which did exactly that. Do not type a
 * number into this file, and do not replace it with a raster that has numbers
 * burned in. The badge must stay visible for as long as the card is illustrative.
 */

/* Rising curve, drawn once. Deliberately irregular — a smooth arc reads as a
 * projection, and a jagged one reads as a record; this is neither, but the
 * badge says so and the shape should not oversell. No y-axis values: the mock's
 * 20%/10%/0%/-10% axis is itself a return claim. */
const CURVE =
  '0,92 12,86 24,89 36,80 48,84 60,74 72,78 84,68 96,71 108,61 120,65 132,55 ' +
  '144,58 156,48 168,52 180,42 192,46 204,36 216,39 228,30 240,33 252,24 ' +
  '264,27 276,18 288,21 300,12'

const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY']

/** The three tiles the dashboard actually shows. Labels are real; values are not shown. */
const TILES = ['Total Return', 'Trades Executed', 'Win Rate']

export default function HeroChartIllustration() {
  return (
    <div className="rounded-2xl border border-[#2B2B2B] bg-[#141414]/80 p-5 shadow-[0_12px_32px_rgba(0,0,0,.28)]">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[15px] text-gray-200">Performance Overview</div>
        {/* Non-negotiable while this card is a drawing. It is the only thing
            separating an illustration from a performance claim. */}
        <span className="rounded-full border border-[#3A3A3A] bg-[#0E0F0F] px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-[#8C8378]">
          Illustration
        </span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2.5">
        {TILES.map((label, i) => (
          <div key={label} className="rounded-lg border border-[#2B2B2B] bg-[#0E0F0F] px-3 py-2.5">
            <div className="text-[11px] leading-tight text-[#B8B8B8]">{label}</div>
            {/* Redaction bar rather than a fake figure. Widths vary so the row
                reads as a designed placeholder, not three identical blanks. */}
            <div
              className="mt-2 h-[13px] rounded-[3px] bg-[#242424]"
              style={{ width: ['64%', '46%', '52%'][i] }}
              aria-hidden
            />
          </div>
        ))}
      </div>

      <div className="mt-4">
        <svg
          viewBox="0 0 300 100"
          className="h-[150px] w-full"
          preserveAspectRatio="none"
          role="img"
          aria-label="Illustration of an upward-trending performance chart. Decorative — it does not show IronForge results."
        >
          <defs>
            <linearGradient id="hero-illus-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22C55E" stopOpacity="0.34" />
              <stop offset="100%" stopColor="#22C55E" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          {[8, 31, 54, 77].map((y) => (
            <line key={y} x1="0" y1={y} x2="300" y2={y} stroke="#242424" strokeWidth="0.6" />
          ))}
          <polygon points={`0,100 ${CURVE} 300,100`} fill="url(#hero-illus-fill)" />
          <polyline
            points={CURVE}
            fill="none"
            stroke="#22C55E"
            strokeWidth="1.7"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        <div className="mt-1.5 flex justify-between px-0.5 text-[10px] tracking-wide text-[#7C7772]">
          {MONTHS.map((m) => (
            <span key={m}>{m}</span>
          ))}
        </div>
      </div>

      <p className="mt-3 border-t border-[#1E1E1E] pt-3 text-[11px] leading-relaxed text-[#B8B8B8]">
        Example of the performance dashboard included with every membership. Illustration only
        &mdash; it does not represent IronForge results, and past performance would not indicate
        future results.
      </p>
    </div>
  )
}
