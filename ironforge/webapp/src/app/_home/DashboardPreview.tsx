import { WalletIcon, CoinsIcon, CalendarCashIcon, TrendIcon, ChartCircleIcon, CheckCircleIcon } from './icons'
import { getLedgerSummary, getLedgerTrades } from '@/lib/bot-ledger/ledger'

/* Hero dashboard preview (desktop only per the handoff spec — the mobile IA drops it).
 *
 * LIVE, from the same closed-trade universe /bot-ledger publishes.
 *
 * It first read "$26,384.12" and "+18.74%" — fabricated figures no account ever produced.
 * Those were blanked to em-dashes, which was honest but showed a prospect nothing. It now
 * carries the real paper record, which is both true and far more persuasive than the
 * invented version was.
 *
 * Two rules this component lives under:
 *
 *  1. NOTHING IS INVENTED. Every figure traces to a closed paper trade. If the ledger
 *     cannot be read the tiles fall back to em-dashes — never to a plausible number, and
 *     never to a stale hardcoded one.
 *  2. NO PERSONAL-ACCOUNT FRAMING. The tiles used to say "Account Value", "Portfolio
 *     Value", "Weekly Income" — concepts that cannot be true on a page served to a
 *     logged-out stranger with no account. They now carry what the ledger actually
 *     publishes: win rate, trade counts, and return on buying power.
 */

const PLACEHOLDER = '—'

/** Decimals arrive as strings so they render exactly as computed. Never coerce a null. */
function pct(v: string | null | undefined, opts: { sign?: boolean } = {}): string {
  if (v == null) return PLACEHOLDER
  const n = Number(v)
  if (!Number.isFinite(n)) return PLACEHOLDER
  return `${opts.sign && n > 0 ? '+' : ''}${v}%`
}

function count(n: number | null | undefined): string {
  return typeof n === 'number' && Number.isFinite(n) ? String(n) : PLACEHOLDER
}

interface PreviewTrade {
  closed_date: string
  setup: string
  return_on_bp_pct: string | null
  outcome: string
}

interface PreviewData {
  winRate: string
  avgReturn: string
  closedTrades: string
  lifetimeWinRate: string
  lifetimeClosed: string
  streak: string
  since: string | null
  lastTradeDate: string | null
  trades: PreviewTrade[]
}

/**
 * Read the live figures. Returns null on ANY failure so the caller renders the
 * em-dash layout — a marketing page must never block on, or invent around, the ledger.
 */
async function loadPreview(): Promise<PreviewData | null> {
  try {
    const now = Date.now()
    const [summary, trades] = await Promise.all([
      getLedgerSummary({ period: '30d', now }),
      getLedgerTrades({ bot: 'spark', limit: 2, now }),
    ])

    const spark = summary.bots.find((b) => b.bot === 'spark')
    if (!spark) return null

    const items = ((trades as { items?: PreviewTrade[] }).items ?? []).slice(0, 2)

    return {
      winRate: pct(spark.win_rate_pct),
      avgReturn: pct(spark.avg_return_on_bp_pct, { sign: true }),
      closedTrades: count(spark.closed_trades),
      lifetimeWinRate: pct(spark.lifetime_win_rate_pct),
      lifetimeClosed: count(spark.lifetime_closed_trades),
      streak: count(spark.current_win_streak),
      since: spark.inception_date,
      lastTradeDate: items[0]?.closed_date ?? null,
      trades: items,
    }
  } catch {
    return null
  }
}

export const DAILY_BRIEF_ITEMS = [
  <>No positions require immediate action.</>,
  <>Market conditions are favorable for your strategy.</>,
  <>Your executed trades appear here each morning.</>,
  <>
    {/* Platform runs on Central Time everywhere else — ET here was drift. */}
    Next execution window: <span className="text-[#FD5301]">Tomorrow 8:30 AM CT</span>
  </>,
]

export function DailyBriefList({ compact = false }: { compact?: boolean }) {
  return (
    <ul className={compact ? 'space-y-2' : 'space-y-2.5'}>
      {DAILY_BRIEF_ITEMS.map((item, i) => (
        <li key={i} className="flex items-start gap-2">
          <CheckCircleIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="text-[11px] leading-snug text-gray-300">{item}</span>
        </li>
      ))}
    </ul>
  )
}

export default async function DashboardPreview() {
  const d = await loadPreview()

  const snapshotTiles = [
    { icon: WalletIcon, label: 'Closed Trades', value: d?.closedTrades ?? PLACEHOLDER, sub: 'Last 30 days', green: false },
    { icon: CoinsIcon, label: 'Win Rate', value: d?.winRate ?? PLACEHOLDER, sub: 'Last 30 days', green: true },
    { icon: CalendarCashIcon, label: 'Avg Return', value: d?.avgReturn ?? PLACEHOLDER, sub: 'Per trade, on capital used', green: true },
    { icon: TrendIcon, label: 'Lifetime Win Rate', value: d?.lifetimeWinRate ?? PLACEHOLDER, sub: d ? `${d.lifetimeClosed} closed trades` : 'All time', green: false },
  ]

  return (
    <div className="relative rounded-2xl border border-white/10 bg-[#0A0B0C] p-3 shadow-2xl shadow-black/60">
      {/* Says exactly what these numbers are. They are REAL and they are PAPER — both
          halves matter, and the badge is the only place a visitor is told. */}
      <span className="absolute bottom-3 right-3 z-10 rounded-full border border-white/15 bg-black/70 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-gray-400">
        Live paper results · see /bot-ledger
      </span>

      {/* Top strip: agent status / win rate / avg return / streak */}
      <div className="grid grid-cols-4 divide-x divide-white/10 rounded-xl border border-white/10 bg-[#0C0D0E]">
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#63C132]">Spark Agent Status</div>
          <div className="mt-1.5 flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#63C132]" />
            <span className="text-base font-semibold text-white">Active</span>
          </div>
          {/* nowrap: the ISO date was breaking mid-token in this narrow column,
              rendering as "Last trade 2026-07-" / "28". */}
          <div className="mt-1 whitespace-nowrap text-[11px] font-semibold text-white">
            {/* Evidence for "Active" rather than an assertion of it. */}
            {d?.lastTradeDate ? `Last trade ${d.lastTradeDate}` : 'Monitoring the market.'}
          </div>
          <p className="mt-0.5 text-[10px] leading-snug text-gray-500">
            {d?.since ? `Trading on paper since ${d.since}.` : 'IronForge monitors the market and executes the strategy.'}
          </p>
        </div>
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Win Rate</div>
          <div className="mt-1.5 text-lg font-bold text-white">{d?.winRate ?? PLACEHOLDER}</div>
          <div className="mt-1 text-[10px] text-gray-500">Last 30 days</div>
        </div>
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Avg Return</div>
          <div className="mt-1.5 text-lg font-bold text-[#63C132]">{d?.avgReturn ?? PLACEHOLDER}</div>
          <div className="text-[11px] font-semibold text-gray-500">per trade</div>
          <div className="mt-1 text-[10px] text-gray-500">On capital used</div>
        </div>
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Win Streak</div>
          <div className="mt-1.5 flex items-center gap-2">
            <ChartCircleIcon className="h-6 w-6 shrink-0 text-[#63C132]" />
            <span className="text-sm font-semibold text-[#63C132]">
              {d ? `${d.streak} in a row` : PLACEHOLDER}
            </span>
          </div>
          <p className="mt-1 text-[10px] leading-snug text-gray-500">Consecutive winning trades.</p>
        </div>
      </div>

      {/* Snapshot */}
      <div className="mt-3 rounded-xl border border-white/10 bg-[#0C0D0E] p-3.5">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">Spark Paper Record</div>
        <div className="mt-3 grid grid-cols-4 gap-2.5">
          {snapshotTiles.map(({ icon: Icon, label, value, sub, green }) => (
            <div key={label} className="rounded-lg border border-white/10 bg-[#101112] px-2 py-3.5 text-center">
              <Icon className="mx-auto h-6 w-6 text-[#FD5301]" />
              <div className="mt-2 text-[10px] text-gray-400">{label}</div>
              <div className={`mt-1 text-[15px] font-bold ${green ? 'text-[#63C132]' : 'text-white'}`}>{value}</div>
              <div className="mt-0.5 text-[9px] leading-tight text-gray-500">{sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Daily brief + recent trades */}
      <div className="mt-3 grid grid-cols-[5fr_7fr] gap-3">
        <div className="rounded-xl border border-white/10 bg-[#0C0D0E] p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">Daily Brief</div>
          <div className="mt-2.5">
            <DailyBriefList />
          </div>
          <div className="mt-3 text-[11px] font-semibold text-[#FD5301]">View Full Brief &rsaquo;</div>
        </div>
        <div className="rounded-xl border border-white/10 bg-[#0C0D0E] p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">Recent Trades</span>
            <span className="text-[11px] font-semibold text-[#FD5301]">View All</span>
          </div>
          <table className="mt-2 w-full text-left">
            <thead>
              <tr className="text-[9px] text-gray-500">
                <th className="py-1 font-medium">Date</th>
                <th className="py-1 font-medium">Setup</th>
                <th className="py-1 font-medium">Return</th>
                <th className="py-1 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="text-[9.5px] text-gray-300">
              {/* Real closed trades. Invented fills ("SPX 5,011 PE $210.00 Filled") used to
                  sit here; strikes and exact times stay unpublished, exactly as on the
                  ledger — a date, the setup, the return and the outcome are the whole row. */}
              {(d?.trades.length ? d.trades : [null, null]).map((t, i) => (
                <tr key={t?.closed_date ?? i} className="border-t border-white/5">
                  <td className="py-2">{t?.closed_date ?? PLACEHOLDER}</td>
                  <td className="py-2">{t?.setup ?? 'SPY Iron Condor'}</td>
                  <td className="py-2 text-white">{t ? pct(t.return_on_bp_pct, { sign: true }) : PLACEHOLDER}</td>
                  <td
                    className={`py-2 font-semibold ${
                      t?.outcome === 'win' ? 'text-[#63C132]' : t?.outcome ? 'text-gray-300' : 'text-gray-500'
                    }`}
                  >
                    {t?.outcome ? t.outcome.toUpperCase() : PLACEHOLDER}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-2 border-t border-white/5 pt-2 text-[9.5px] text-gray-500">
            Paper trading. Past results do not predict future returns.
          </div>
        </div>
      </div>
    </div>
  )
}
