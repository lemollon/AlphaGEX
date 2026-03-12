'use client'

import Link from 'next/link'
import dynamic from 'next/dynamic'

const LaunchCountdown = dynamic(() => import('@/components/LaunchCountdown'), {
  ssr: false,
  loading: () => (
    <div className="rounded-xl border border-amber-500/20 bg-forge-card/80 p-6">
      <div className="h-20 animate-pulse rounded bg-forge-border/30" />
    </div>
  ),
})

const botIcons: Record<string, React.ReactNode> = {
  FLAME: <img src="/icon-flame.svg" alt="" className="h-5 w-5 inline-block mr-1.5 align-[-3px]" />,
  SPARK: <img src="/icon-spark.svg" alt="" className="h-5 w-5 inline-block mr-1.5 align-[-3px]" />,
  INFERNO: <img src="/inferno-icon.svg" alt="" className="h-5 w-5 inline-block mr-1.5 align-[-3px]" />,
}

const botGlow: Record<string, string> = {
  FLAME: 'glow-flame',
  SPARK: 'glow-spark',
  INFERNO: 'glow-inferno',
}

/* ── Strategy Configuration (from BotConfig) ───────────────────────── */

const sharedConfig = {
  ticker: 'SPY',
  startingCapital: '$10,000',
  riskPerTrade: '15%',
  spreadWidth: '$5.00',
  sdMultiplier: '1.2x',
  profitTarget: '30%',
  stopLoss: '100%',
  maxContracts: 10,
  maxTradesPerDay: 1,
  vixSkipThreshold: 32,
  minCredit: '$0.05',
  buyingPowerUsage: '85%',
  pdtLimit: '3 / 5 rolling days',
  eodCutoff: '2:45 PM CT',
  entryWindow: '8:30 AM – 2:00 PM CT',
  scanFrequency: 'Every 1 min',
  mtmFailLimit: 10,
}

const configRows: Array<{ label: string; value: string; hint?: string }> = [
  { label: 'Ticker', value: sharedConfig.ticker },
  { label: 'Starting Capital', value: sharedConfig.startingCapital, hint: 'Paper account' },
  { label: 'Risk Per Trade', value: sharedConfig.riskPerTrade, hint: 'Of account' },
  { label: 'Spread Width', value: sharedConfig.spreadWidth, hint: 'Per leg' },
  { label: 'Strike SD', value: sharedConfig.sdMultiplier, hint: 'Expected move multiplier' },
  { label: 'Profit Target', value: '30/20/15%', hint: 'Sliding (time-based)' },
  { label: 'Stop Loss', value: sharedConfig.stopLoss, hint: 'Of entry credit' },
  { label: 'Max Contracts', value: String(sharedConfig.maxContracts), hint: 'Per trade' },
  { label: 'Max Trades/Day', value: String(sharedConfig.maxTradesPerDay) },
  { label: 'VIX Skip', value: `> ${sharedConfig.vixSkipThreshold}`, hint: 'No entry' },
  { label: 'Min Credit', value: sharedConfig.minCredit, hint: 'Per spread' },
  { label: 'Buying Power Use', value: sharedConfig.buyingPowerUsage },
  { label: 'PDT Limit', value: sharedConfig.pdtLimit, hint: 'Rolling window' },
]

const scheduleRows: Array<{ label: string; value: string }> = [
  { label: 'Entry Window', value: sharedConfig.entryWindow },
  { label: 'EOD Cutoff', value: sharedConfig.eodCutoff },
  { label: 'Scan Frequency', value: sharedConfig.scanFrequency },
  { label: 'MTM Fail Limit', value: `${sharedConfig.mtmFailLimit} consecutive` },
]

/* ── Bots ───────────────────────────────────────────────────────────── */

const bots = [
  {
    name: 'SPARK',
    href: '/spark',
    dte: '1DTE',
    desc: 'Shorter-duration Iron Condors with 1 day to expiration. Faster theta decay, quicker resolution.',
    border: 'border-blue-500/30 hover:border-blue-400/60',
    heading: 'text-blue-400',
    btn: 'border-blue-500/60 text-blue-400 hover:bg-blue-500/10',
    glow: 'shadow-blue-500/5',
    badge: 'bg-blue-500/15 text-blue-400',
  },
  {
    name: 'FLAME',
    href: '/flame',
    dte: '2DTE',
    desc: 'Longer-duration Iron Condors with 2 days to expiration. More premium, more time for the trade to work.',
    border: 'border-amber-500/30 hover:border-amber-400/60',
    heading: 'text-amber-400',
    btn: 'border-amber-500/60 text-amber-400 hover:bg-amber-500/10',
    glow: 'shadow-amber-500/5',
    badge: 'bg-amber-500/15 text-amber-400',
  },
  {
    name: 'INFERNO',
    href: '/inferno',
    dte: '0DTE',
    desc: 'FORTRESS-style 0DTE Iron Condors. Up to 3 trades per day with multiple simultaneous positions.',
    border: 'border-red-500/30 hover:border-red-400/60',
    heading: 'text-red-400',
    btn: 'border-red-500/60 text-red-400 hover:bg-red-500/10',
    glow: 'shadow-red-500/5',
    badge: 'bg-red-500/15 text-red-400',
  },
  {
    name: 'Compare',
    href: '/compare',
    dte: 'Head to Head',
    desc: 'Side-by-side comparison of FLAME and SPARK. Equity curves, win rates, P&L, and all metrics.',
    border: 'border-stone-600/30 hover:border-stone-500/60',
    heading: 'text-white',
    btn: 'border-stone-500/60 text-gray-300 hover:bg-stone-700/30',
    glow: '',
    badge: 'bg-stone-500/15 text-stone-300',
  },
]

/* ── Exit Logic ─────────────────────────────────────────────────────── */

const exitRules = [
  { trigger: 'PT (Morning)', condition: '30%  8:30–10:29 AM CT', color: 'text-emerald-400' },
  { trigger: 'PT (Midday)', condition: '20%  10:30 AM–12:59 PM CT', color: 'text-yellow-400' },
  { trigger: 'PT (Afternoon)', condition: '15%  1:00–2:44 PM CT', color: 'text-orange-400' },
  { trigger: 'Stop Loss', condition: '100%  Cost ≥ 200% of credit', color: 'text-red-400' },
  { trigger: 'EOD Cutoff', condition: '2:45 PM CT', color: 'text-amber-400' },
  { trigger: 'Stale/Expired', condition: 'Position from prior day', color: 'text-amber-400' },
  { trigger: 'Data Failure', condition: '10 MTM failures', color: 'text-red-400' },
]

/* ── Page ────────────────────────────────────────────────────────────── */

export default function Home() {
  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="text-center mt-2">
        <h1 className="text-5xl font-extrabold tracking-tight mb-2 glow-amber">
          <img src="/ironforge-logo.svg" alt="" className="h-10 w-10 inline-block align-middle" />{' '}
          <span className="text-white">Iron</span>
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-orange-400 to-amber-500">
            Forge
          </span>
        </h1>
        <p className="text-forge-muted text-sm mb-3">
          SPY Iron Condor Paper Trading &middot; Databricks + Tradier
        </p>
        <p style={{
          color: '#F59E0B',
          fontStyle: 'italic',
          fontSize: '0.75rem',
          fontFamily: "Georgia, 'Times New Roman', serif",
          letterSpacing: '0.05em',
          textAlign: 'center',
          maxWidth: '400px',
          margin: '4px auto 0 auto',
          opacity: 1,
        }}>
          &ldquo;As iron sharpens iron, so one person sharpens another.&rdquo; &mdash; Proverbs 27:17
        </p>
      </div>

      {/* Launch Countdown */}
      <LaunchCountdown />

      {/* Bot Cards */}
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
        {bots.map((bot) => (
          <Link key={bot.name} href={bot.href}>
            <div
              className={`rounded-xl border bg-forge-card/80 p-6 h-full transition-all duration-200 hover:translate-y-[-2px] ${bot.border} ${bot.glow}`}
            >
              <div className="flex items-center justify-between mb-3">
                <h2 className={`text-2xl font-bold ${bot.heading} ${botGlow[bot.name] || ''}`}>
                  {botIcons[bot.name]}{bot.name}
                </h2>
                <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${bot.badge}`}>
                  {bot.dte}
                </span>
              </div>
              <p className="text-sm text-gray-400 mb-5 leading-relaxed">{bot.desc}</p>
              <div className="text-center">
                <span className={`inline-block px-5 py-1.5 rounded-lg border text-sm font-medium transition-colors ${bot.btn}`}>
                  View Dashboard &rarr;
                </span>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* Strategy Configuration */}
      <section>
        <h2 className="text-xl font-bold mb-1">
          <span className="text-amber-400">Strategy</span> Configuration
        </h2>
        <p className="text-xs text-forge-muted mb-5">
          Shared parameters for both FLAME and SPARK &mdash; only DTE differs
        </p>

        <div className="grid md:grid-cols-2 gap-5">
          {/* Left: IC Parameters */}
          <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
            <h3 className="text-sm font-semibold text-amber-400/80 uppercase tracking-wider mb-4">
              Iron Condor Parameters
            </h3>
            <div className="space-y-2.5">
              {configRows.map((row) => (
                <div key={row.label} className="flex items-baseline justify-between">
                  <span className="text-sm text-gray-400">{row.label}</span>
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-gray-100">{row.value}</span>
                    {row.hint && (
                      <span className="text-[10px] text-forge-muted">{row.hint}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Right: Schedule + Exit Rules */}
          <div className="space-y-5">
            {/* Schedule */}
            <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
              <h3 className="text-sm font-semibold text-amber-400/80 uppercase tracking-wider mb-4">
                Trading Schedule
              </h3>
              <div className="space-y-2.5">
                {scheduleRows.map((row) => (
                  <div key={row.label} className="flex items-baseline justify-between">
                    <span className="text-sm text-gray-400">{row.label}</span>
                    <span className="text-sm font-medium text-gray-100">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Exit Rules */}
            <div className="rounded-xl border border-forge-border bg-forge-card/60 p-5">
              <h3 className="text-sm font-semibold text-amber-400/80 uppercase tracking-wider mb-4">
                Exit Rules
              </h3>
              <div className="space-y-2">
                {exitRules.map((rule) => (
                  <div key={rule.trigger} className="flex items-center justify-between text-sm">
                    <span className={`font-medium ${rule.color}`}>{rule.trigger}</span>
                    <span className="text-gray-400 text-xs">{rule.condition}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* Signal Flow */}
      <section>
        <h2 className="text-xl font-bold mb-4">
          <span className="text-amber-400">Signal</span> Flow
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { step: '1', title: 'Market Data', desc: 'SPY spot + VIX from Tradier production API', icon: '&#9673;' },
            { step: '2', title: 'Filter Gates', desc: 'VIX < 32, not max trades, PDT compliant, within window', icon: '&#9670;' },
            { step: '3', title: 'Strike Calc', desc: 'SD-based strikes, $5 wings, real option chain credits', icon: '&#9651;' },
            { step: '4', title: 'Execute', desc: 'Size position, log to Delta Lake, monitor MTM every 1 min', icon: '&#9632;' },
          ].map((s) => (
            <div key={s.step} className="rounded-xl border border-forge-border bg-forge-card/40 p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-amber-500 text-lg" dangerouslySetInnerHTML={{ __html: s.icon }} />
                <span className="text-xs text-forge-muted font-mono">STEP {s.step}</span>
              </div>
              <p className="text-sm font-semibold text-gray-100 mb-1">{s.title}</p>
              <p className="text-xs text-gray-500 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* DTE Comparison */}
      <section>
        <h2 className="text-xl font-bold mb-4">
          <span className="text-amber-400">FLAME</span> vs <span className="text-blue-400">SPARK</span>
        </h2>
        <div className="rounded-xl border border-forge-border bg-forge-card/60 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-forge-border">
                <th className="text-left py-3 px-4 text-forge-muted font-medium">Parameter</th>
                <th className="text-center py-3 px-4 text-amber-400 font-semibold">FLAME</th>
                <th className="text-center py-3 px-4 text-blue-400 font-semibold">SPARK</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-forge-border/50">
              {[
                { param: 'Days to Expiration', flame: '2 DTE', spark: '1 DTE', diff: true },
                { param: 'Spread Width', flame: '$5.00', spark: '$5.00', diff: false },
                { param: 'Profit Target', flame: '30/20/15%', spark: '30/20/15%', diff: false },
                { param: 'Stop Loss', flame: '100%', spark: '100%', diff: false },
                { param: 'Max Contracts', flame: '10', spark: '10', diff: false },
                { param: 'SD Multiplier', flame: '1.2x', spark: '1.2x', diff: false },
                { param: 'Theta Decay', flame: 'Slower', spark: 'Faster', diff: true },
                { param: 'Max Trades/Day', flame: '1', spark: '1', diff: false },
                { param: 'Premium', flame: 'Higher', spark: 'Lower', diff: true },
                { param: 'Resolution', flame: '~2 days', spark: '~1 day', diff: true },
              ].map((row) => (
                <tr key={row.param}>
                  <td className="py-2.5 px-4 text-gray-400">{row.param}</td>
                  <td className={`py-2.5 px-4 text-center font-medium ${row.diff ? 'text-amber-400' : 'text-gray-300'}`}>
                    {row.flame}
                  </td>
                  <td className={`py-2.5 px-4 text-center font-medium ${row.diff ? 'text-blue-400' : 'text-gray-300'}`}>
                    {row.spark}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Fire divider */}
      <div className="fire-divider" />

      {/* System Footer */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm pb-4">
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Platform</p>
          <p className="font-medium">Databricks</p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Data Source</p>
          <p className="font-medium">Tradier <span className="text-emerald-400 text-xs">(Production)</span></p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Storage</p>
          <p className="font-medium">Delta Lake</p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Ticker</p>
          <p className="font-medium">SPY</p>
        </div>
        <div>
          <p className="text-forge-muted text-xs mb-0.5">Mode</p>
          <span className="inline-block px-2 py-0.5 rounded text-xs bg-amber-500/15 text-amber-400 font-medium">
            PAPER
          </span>
        </div>
      </div>
    </div>
  )
}
