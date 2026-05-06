'use client'

import { useState } from 'react'

interface AccountResult {
  name: string
  account_id: string | null
  positions_found: number
  positions_closed: number
  positions_failed: number
  buying_power_before: number | null
  buying_power_after: number | null
  details: Array<{
    symbol: string
    quantity: number
    status: string
    method?: string
    error?: string
  }>
}

interface PaperResult {
  bot: string
  dte: string
  positions_closed: number
}

interface EmergencyResult {
  sandbox_results: AccountResult[]
  paper_results: PaperResult[]
  summary: {
    sandbox_positions_closed: number
    sandbox_positions_failed: number
    paper_positions_closed: number
    any_negative_bp_remaining: boolean
    recommendation: string
  }
}

interface DiagnosticResult {
  accounts: Array<{
    name: string
    account_id: string | null
    buying_power: number | null
    positions: Array<{ symbol: string; quantity: number }>
  }>
  total_positions: number
  any_negative_bp: boolean
}

export default function SandboxKillSwitch() {
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [diagLoading, setDiagLoading] = useState(false)
  const [result, setResult] = useState<EmergencyResult | null>(null)
  const [diagnostic, setDiagnostic] = useState<DiagnosticResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function runDiagnostic() {
    setDiagLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/sandbox/emergency-close')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setDiagnostic(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setDiagLoading(false)
    }
  }

  async function executeKillSwitch() {
    setLoading(true)
    setError(null)
    setShowConfirm(false)
    try {
      const res = await fetch('/api/sandbox/emergency-close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: 'manual',
          caller: 'SandboxKillSwitch.tsx',
          reason: 'operator pressed EMERGENCY CLOSE ALL button',
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setResult(data)
      setDiagnostic(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-red-500/40 bg-red-950/20 p-4">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-red-400 text-lg font-bold">SANDBOX KILL SWITCH</span>
        <span className="text-xs text-red-400/60">Emergency Close All Positions</span>
      </div>

      <div className="flex gap-2 mb-3">
        <button
          onClick={runDiagnostic}
          disabled={diagLoading}
          className="text-xs px-3 py-1.5 rounded-lg border border-stone-600 text-gray-300 hover:bg-stone-700/30 transition-colors disabled:opacity-50"
        >
          {diagLoading ? 'Checking...' : 'Check Sandbox Status'}
        </button>
        <button
          onClick={() => setShowConfirm(true)}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg border border-red-500/60 text-red-400 hover:bg-red-500/10 font-semibold transition-colors disabled:opacity-50"
        >
          {loading ? 'Closing All Positions...' : 'EMERGENCY CLOSE ALL'}
        </button>
      </div>

      {/* Diagnostic results */}
      {diagnostic && (
        <div className="text-xs space-y-2 mb-3">
          <p className="text-gray-400">
            Total sandbox positions: <span className="text-white font-mono">{diagnostic.total_positions}</span>
            {diagnostic.any_negative_bp && (
              <span className="ml-2 text-red-400 font-semibold">NEGATIVE BP DETECTED</span>
            )}
          </p>
          {diagnostic.accounts.map((acct) => (
            <div key={acct.name} className="pl-3 border-l border-forge-border">
              <span className="text-gray-300 font-medium">{acct.name}</span>
              <span className="text-gray-500 ml-2">
                BP: {acct.buying_power != null ? (
                  <span className={acct.buying_power < 0 ? 'text-red-400' : 'text-emerald-400'}>
                    ${acct.buying_power.toFixed(2)}
                  </span>
                ) : 'N/A'}
              </span>
              <span className="text-gray-500 ml-2">{acct.positions.length} positions</span>
            </div>
          ))}
        </div>
      )}

      {/* Confirmation dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="bg-forge-card border border-red-500/40 rounded-xl p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-bold text-red-400 mb-3">CONFIRM: Emergency Close All</h3>
            <p className="text-sm text-gray-300 mb-2">This will:</p>
            <ul className="text-sm text-gray-400 list-disc list-inside mb-4 space-y-1">
              <li>Close ALL sandbox positions in User, Matt, and Logan accounts</li>
              <li>Force-close ALL open paper positions in FLAME, SPARK, and INFERNO</li>
              <li>Reconcile all paper account balances</li>
              <li>Log everything to the activity log</li>
            </ul>
            <p className="text-xs text-amber-400 mb-4">
              Paper positions will be closed at entry credit (P&L = $0).
              Sandbox orders may fail if market is closed — expired options settle overnight.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowConfirm(false)}
                className="px-4 py-2 text-sm rounded-lg border border-forge-border text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={executeKillSwitch}
                className="px-4 py-2 text-sm rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium transition-colors"
              >
                EXECUTE KILL SWITCH
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="text-xs space-y-2 border-t border-forge-border/50 pt-3">
          <p className="font-medium text-white">Results:</p>
          <p className="text-gray-400">
            Sandbox: {result.summary.sandbox_positions_closed} closed, {result.summary.sandbox_positions_failed} failed
          </p>
          <p className="text-gray-400">
            Paper: {result.summary.paper_positions_closed} positions force-closed
          </p>
          {result.sandbox_results.map((acct) => (
            <div key={acct.name} className="pl-3 border-l border-forge-border">
              <span className="text-gray-300 font-medium">{acct.name}</span>
              <span className="text-gray-500 ml-2">
                {acct.positions_closed}/{acct.positions_found} closed
              </span>
              {acct.buying_power_after != null && (
                <span className={`ml-2 ${acct.buying_power_after < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                  BP: ${acct.buying_power_after.toFixed(2)}
                </span>
              )}
            </div>
          ))}
          {result.summary.any_negative_bp_remaining && (
            <p className="text-amber-400 font-medium mt-2">
              BP still negative — expired options may need overnight settlement.
              Consider switching FLAME to paper-only mode.
            </p>
          )}
          <p className="text-gray-500 mt-1">{result.summary.recommendation}</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-xs text-red-400 mt-2">Error: {error}</p>
      )}
    </div>
  )
}
