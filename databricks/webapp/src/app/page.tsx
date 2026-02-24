'use client'

import Link from 'next/link'

const bots = [
  {
    name: 'FLAME',
    href: '/flame',
    dte: '2DTE',
    desc: 'Longer-duration Iron Condors with 2 days to expiration. More premium, more time for the trade to work.',
    accent: 'amber',
    border: 'border-amber-500/30 hover:border-amber-500/60',
    heading: 'text-amber-400',
    btn: 'border-amber-500 text-amber-400 hover:bg-amber-500/10',
  },
  {
    name: 'SPARK',
    href: '/spark',
    dte: '1DTE',
    desc: 'Shorter-duration Iron Condors with 1 day to expiration. Faster theta decay, quicker resolution.',
    accent: 'blue',
    border: 'border-blue-500/30 hover:border-blue-500/60',
    heading: 'text-blue-400',
    btn: 'border-blue-500 text-blue-400 hover:bg-blue-500/10',
  },
  {
    name: 'Compare',
    href: '/compare',
    dte: 'Head to Head',
    desc: 'Side-by-side comparison of FLAME and SPARK. Equity curves, win rates, P&L, and all performance metrics.',
    accent: 'gray',
    border: 'border-slate-600/30 hover:border-slate-500/60',
    heading: 'text-white',
    btn: 'border-slate-500 text-gray-300 hover:bg-slate-700/50',
  },
]

export default function Home() {
  return (
    <div>
      <div className="text-center mb-10 mt-4">
        <h1 className="text-4xl font-bold mb-2">
          <span className="text-white">Iron</span>
          <span className="text-amber-400">Forge</span>
        </h1>
        <p className="text-gray-500">
          FLAME vs SPARK Iron Condor Paper Trading on Databricks
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-6 mb-10">
        {bots.map((bot) => (
          <Link key={bot.name} href={bot.href}>
            <div
              className={`rounded-lg border bg-slate-900/50 p-6 h-full transition-colors ${bot.border}`}
            >
              <h2 className={`text-2xl font-bold text-center mb-1 ${bot.heading}`}>
                {bot.name}
              </h2>
              <p className="text-sm text-gray-500 text-center mb-4">{bot.dte}</p>
              <p className="text-sm text-gray-400 text-center mb-6">{bot.desc}</p>
              <div className="text-center">
                <span className={`inline-block px-4 py-1.5 rounded border text-sm ${bot.btn}`}>
                  View Dashboard
                </span>
              </div>
            </div>
          </Link>
        ))}
      </div>

      <hr className="border-slate-800" />

      <div className="mt-6 grid grid-cols-4 gap-6 text-sm">
        <div>
          <p className="text-gray-600 text-xs">Platform</p>
          <p className="font-medium">Databricks (Delta Lake)</p>
        </div>
        <div>
          <p className="text-gray-600 text-xs">Data Source</p>
          <p className="font-medium">Tradier API (Production)</p>
        </div>
        <div>
          <p className="text-gray-600 text-xs">Ticker</p>
          <p className="font-medium">SPY</p>
        </div>
        <div>
          <p className="text-gray-600 text-xs">Mode</p>
          <span className="inline-block px-2 py-0.5 rounded text-xs bg-cyan-500/20 text-cyan-400">
            PAPER
          </span>
        </div>
      </div>
    </div>
  )
}
