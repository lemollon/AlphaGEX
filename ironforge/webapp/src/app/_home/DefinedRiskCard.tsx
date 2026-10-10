/**
 * The hero card: what a worst day costs.
 *
 * REPLACES PerformanceOverviewCard, which plotted the closed-trade ledger. Three
 * reasons it went, in order of how much they matter:
 *
 *  1. The curve was not "an account". `loadBot` in lib/live/track-record.ts selects
 *     every closed row for the bot with NO `account_type` or `person` predicate, so
 *     sandbox and production were summed into one cumulative line — while the badge
 *     above it read "Paper account", because `MODE` is a hardcoded constant rather
 *     than something derived from the rows.
 *  2. Spark's structure changed. The 1DTE iron condor was retired after a 972-cell
 *     sweep on real fills found no edge; Spark now runs a different structure. A
 *     single unbroken line across both implies one continuous product.
 *  3. Even fixed, a performance chart is the wrong hero. It is weakest exactly when
 *     a prospect is most sceptical — a short record, a flat month, a drawdown — and
 *     it answers a question ("what did it return?") that we cannot answer honestly
 *     at this stage without a much longer live sample.
 *
 * This card answers a different question, the one a first-time visitor actually
 * has: HOW MUCH CAN THIS LOSE ME? It describes the instrument rather than the
 * outcome, so it is equally true after a great month and a terrible one, and it
 * cannot go stale. It reads no database and has no failure state.
 *
 * ── Two rules this component lives under ─────────────────────────────────────
 *
 *  NO NUMBERS. Not on the axes, not in the copy. The marketing spec forbids
 *  strategy logic, timing windows, and risk thresholds on this page, and a
 *  labelled axis here would publish the wing width. It is also the honest
 *  choice: the actual floor scales with position size, so any single figure
 *  printed here would be wrong for almost every reader. The SHAPE is the claim.
 *
 *  NO PERFORMANCE. If someone later wants a return, a win rate or a curve back on
 *  this page, it does not belong in this component — and per the note above, it
 *  does not belong in the hero at all until the live record under the current
 *  structure is long enough to mean something.
 */

/* Payoff geometry for a defined-risk credit spread at expiry.
 *
 * Piecewise-linear with exactly three segments, hand-placed rather than computed:
 * lib/ic-payoff.ts would give the same four points but only after being fed
 * strikes, and any strikes chosen here would be invented. The shape is what is
 * being asserted, so it is stated directly.
 *
 * Coordinates are viewBox units. Y is inverted (SVG origin is top-left), so a
 * LARGER y is a WORSE outcome. */
const FLOOR_Y = 168 // max loss — the long wing caps the payoff here
const ZERO_Y = 118 // break-even
const CEIL_Y = 62 // max profit — the credit received
const BREAK_X = 160 // where the long wing stops absorbing
const CEIL_X = 250 // where the short strike is cleared

/* Where the payoff line crosses break-even, solved rather than eyeballed so the
 * two tinted regions meet exactly on the zero line. A single fill spanning both
 * sides was the first version and it was wrong in the worst way: it painted the
 * loss region in the profit colour, so the flat max-loss shelf read as a gain. */
const CROSS_X = BREAK_X + ((FLOOR_Y - ZERO_Y) / (FLOOR_Y - CEIL_Y)) * (CEIL_X - BREAK_X)

export default function DefinedRiskCard() {
  return (
    <div className="rounded-2xl border border-[#2B2B2B] bg-[#141414]/80 p-5 shadow-[0_12px_32px_rgba(0,0,0,.28)]">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm text-gray-200">Every trade has a floor</div>
        <span className="rounded-full border border-[#1E466F] bg-[#10233A] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[#7FB3F0]">
          By structure
        </span>
      </div>

      <p className="mt-3 text-[13px] leading-relaxed text-[#B8B8B8]">
        Both ends are fixed before the position opens.
      </p>

      <svg
        viewBox="0 0 460 200"
        className="mt-2 h-auto w-full"
        role="img"
        aria-label={
          'Payoff diagram for a defined-risk credit spread at expiry. The loss side is flat: ' +
          'below a certain price the long wing caps the loss, so it cannot get worse however far ' +
          'the market falls. Between that point and the short strike the payoff rises. Above the ' +
          'short strike it is flat again at the credit received, which is the most the trade can make.'
        }
      >
        {/* Left rule, trimmed to the data range. It ran the full height first and
            read as an axis stub, which invites the eye to look for tick labels that
            deliberately are not there. */}
        <line x1="30" y1={CEIL_Y - 10} x2="30" y2={FLOOR_Y + 10} stroke="#2B2B2B" strokeWidth="1" />

        {/* Loss side, warm. Flat, which is the entire claim: it does not get
            worse however far the market falls. */}
        <path
          d={`M30,${ZERO_Y} L30,${FLOOR_Y} L${BREAK_X},${FLOOR_Y} L${CROSS_X},${ZERO_Y} Z`}
          fill="#EE5A24"
          fillOpacity="0.14"
        />
        {/* Profit side, cool. Also flat once the short strike is cleared. */}
        <path
          d={`M${CROSS_X},${ZERO_Y} L${CEIL_X},${CEIL_Y} L440,${CEIL_Y} L440,${ZERO_Y} Z`}
          fill="#3B82F6"
          fillOpacity="0.14"
        />

        {/* Break-even, drawn over the fills so both regions read against it.
            Deliberately unlabelled: a lone "0" beside two wordmark labels and no
            other figure looked like a number someone forgot to finish, and the
            warm/cool split already tells the reader which side of it they are on. */}
        <line x1="30" y1={ZERO_Y} x2="440" y2={ZERO_Y} stroke="#3A3A3A" strokeWidth="1" strokeDasharray="4 4" />

        {/* The payoff itself. */}
        <polyline
          points={`30,${FLOOR_Y} ${BREAK_X},${FLOOR_Y} ${CEIL_X},${CEIL_Y} 440,${CEIL_Y}`}
          fill="none"
          stroke="#6E6A66"
          strokeWidth="2"
          strokeLinejoin="round"
        />

        {/* The floor, emphasised — this is the whole point of the card, so it is
            the heaviest mark on it. Brand orange rather than a red: orange against
            the blue payoff clears the colour-vision separation check by a wide
            margin (ΔE 29.5 protan) where a green/red pair does not. */}
        <line
          x1="30"
          y1={FLOOR_Y}
          x2={BREAK_X}
          y2={FLOOR_Y}
          stroke="#EE5A24"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <circle cx={BREAK_X} cy={FLOOR_Y} r="4" fill="#EE5A24" stroke="#141414" strokeWidth="2" />
        <text x="30" y="192" fill="#F0794B" fontSize="10" letterSpacing="0.5" fontFamily="ui-monospace, monospace">
          MOST IT CAN LOSE — KNOWN IN ADVANCE
        </text>

        <line
          x1={CEIL_X}
          y1={CEIL_Y}
          x2="440"
          y2={CEIL_Y}
          stroke="#3B82F6"
          strokeWidth="5"
          strokeLinecap="round"
        />
        <text x="300" y="52" fill="#7FB3F0" fontSize="10" letterSpacing="0.5" fontFamily="ui-monospace, monospace">
          MOST IT CAN MAKE
        </text>

      </svg>

      <p className="mt-3 border-t border-[#1E1E1E] pt-3 text-[11px] leading-relaxed text-[#B8B8B8]">
        No trade can lose more than the floor, whatever the market does overnight. That number is
        set when the position opens — not discovered afterwards.
      </p>
    </div>
  )
}
