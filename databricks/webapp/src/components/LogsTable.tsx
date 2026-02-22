'use client'

interface LogEntry {
  timestamp: string
  level: string
  message: string
  details: string | null
}

const levelColors: Record<string, string> = {
  TRADE_OPEN: 'bg-emerald-500/20 text-emerald-400',
  TRADE_CLOSE: 'bg-blue-500/20 text-blue-400',
  SKIP: 'bg-slate-600/30 text-gray-400',
  ERROR: 'bg-red-500/20 text-red-400',
  RECOVERY: 'bg-amber-500/20 text-amber-400',
  INFO: 'bg-slate-600/30 text-gray-300',
  SCAN: 'bg-slate-600/30 text-gray-400',
}

export default function LogsTable({ logs }: { logs: LogEntry[] }) {
  if (!logs.length) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-6 text-center">
        <p className="text-gray-500">No logs yet</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/50 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700 text-gray-400 text-xs">
            <th className="text-left p-3">Time</th>
            <th className="text-left p-3">Level</th>
            <th className="text-left p-3">Message</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log, i) => (
            <tr key={i} className="border-b border-slate-800 hover:bg-slate-800/80">
              <td className="p-3 text-xs text-gray-400 whitespace-nowrap">
                {log.timestamp?.slice(0, 19)}
              </td>
              <td className="p-3">
                <span className={`text-xs px-2 py-0.5 rounded ${levelColors[log.level] || 'bg-slate-600/30 text-gray-400'}`}>
                  {log.level}
                </span>
              </td>
              <td className="p-3 text-xs text-gray-300">{log.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
