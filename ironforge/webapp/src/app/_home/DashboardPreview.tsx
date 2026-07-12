import { WalletIcon, CoinsIcon, CalendarCashIcon, TrendIcon, ChartCircleIcon, CheckCircleIcon } from './icons'

/* Illustrative hero dashboard preview (desktop only per the handoff spec — the
 * mobile IA drops it entirely). All figures are the approved static copy from
 * the rendering, not live data. */

const WEALTH_TILES = [
  { icon: WalletIcon, label: 'Portfolio Value', value: '$26,384.12', sub: ' ', green: false },
  { icon: CoinsIcon, label: 'Weekly Income', value: '$214.36', sub: 'This Week', green: false },
  { icon: CalendarCashIcon, label: 'Monthly Income', value: '$842.50', sub: 'This Month', green: false },
  { icon: TrendIcon, label: 'Lifetime Return', value: '+18.74%', sub: 'All Time', green: true },
]

export const DAILY_BRIEF_ITEMS = [
  <>No positions require immediate action.</>,
  <>Market conditions are favorable for your strategy.</>,
  <>IronForge executed 2 trades yesterday.</>,
  <>
    Next execution window: <span className="text-[#FD5301]">Tomorrow 9:30 AM ET</span>
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

export default function DashboardPreview() {
  return (
    <div className="rounded-2xl border border-white/10 bg-[#0A0B0C] p-3 shadow-2xl shadow-black/60">
      {/* Top strip: agent status / account value / P&L / outlook */}
      <div className="grid grid-cols-4 divide-x divide-white/10 rounded-xl border border-white/10 bg-[#0C0D0E]">
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#63C132]">Spark Agent Status</div>
          <div className="mt-1.5 flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#63C132]" />
            <span className="text-base font-semibold text-white">Active</span>
          </div>
          <div className="mt-1 text-[11px] font-semibold text-white">No action required.</div>
          <p className="mt-0.5 text-[10px] leading-snug text-gray-500">
            IronForge is monitoring the market and executing your strategy.
          </p>
        </div>
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Account Value</div>
          <div className="mt-1.5 text-lg font-bold text-white">$26,384.12</div>
          <div className="mt-1 text-[10px] text-gray-500">All Accounts</div>
        </div>
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Today&apos;s P&amp;L</div>
          <div className="mt-1.5 text-lg font-bold text-[#63C132]">+$214.36</div>
          <div className="text-[11px] font-semibold text-[#63C132]">(+0.82%)</div>
          <div className="mt-1 text-[10px] text-gray-500">Since market open</div>
        </div>
        <div className="p-3.5">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">Market Outlook</div>
          <div className="mt-1.5 flex items-center gap-2">
            <ChartCircleIcon className="h-6 w-6 shrink-0 text-[#63C132]" />
            <span className="text-sm font-semibold text-[#63C132]">Favorable</span>
          </div>
          <p className="mt-1 text-[10px] leading-snug text-gray-500">Conditions are generally favorable.</p>
        </div>
      </div>

      {/* Wealth snapshot */}
      <div className="mt-3 rounded-xl border border-white/10 bg-[#0C0D0E] p-3.5">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-300">Wealth Snapshot</div>
        <div className="mt-3 grid grid-cols-4 gap-2.5">
          {WEALTH_TILES.map(({ icon: Icon, label, value, sub, green }) => (
            <div key={label} className="rounded-lg border border-white/10 bg-[#101112] px-2 py-3.5 text-center">
              <Icon className="mx-auto h-6 w-6 text-[#FD5301]" />
              <div className="mt-2 text-[10px] text-gray-400">{label}</div>
              <div className={`mt-1 text-[15px] font-bold ${green ? 'text-[#63C132]' : 'text-white'}`}>{value}</div>
              <div className="mt-0.5 text-[9px] text-gray-500">{sub}</div>
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
                <th className="py-1 font-medium">Time</th>
                <th className="py-1 font-medium">Strategy</th>
                <th className="py-1 font-medium">Contract</th>
                <th className="py-1 font-medium">Premium</th>
                <th className="py-1 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="text-[9.5px] text-gray-300">
              <tr className="border-t border-white/5">
                <td className="py-2">May 20, 3:32 PM</td>
                <td className="py-2">SPX Iron Condor</td>
                <td className="py-2">SPX 5,011 PE</td>
                <td className="py-2 text-white">$210.00</td>
                <td className="py-2 font-semibold text-[#63C132]">Filled</td>
              </tr>
              <tr className="border-t border-white/5">
                <td className="py-2">May 20, 9:41 AM</td>
                <td className="py-2">SPX Iron Condor</td>
                <td className="py-2">SPX 5,010 TE</td>
                <td className="py-2 text-white">$195.00</td>
                <td className="py-2 font-semibold text-[#63C132]">Filled</td>
              </tr>
            </tbody>
          </table>
          <div className="mt-2 border-t border-white/5 pt-2 text-[9.5px] text-gray-500">
            All times ET. Updates every 60 seconds.
          </div>
        </div>
      </div>
    </div>
  )
}
