'use client'

import { useState, useEffect, useCallback } from 'react'

/* ── Types ─────────────────────────────────────────────────────── */

interface Account {
  id: number
  person: string
  account_id: string
  api_key_masked: string
  bot: string
  type: string
  is_active: boolean
  capital_pct: number
  pdt_enabled: boolean
  /** Live Tradier total equity (null if unreachable) */
  live_balance: number | null
  /** Live Tradier option buying power */
  live_buying_power: number | null
  /** Number of open positions at Tradier */
  open_positions: number
  /** = live_balance * capital_pct / 100 */
  allocated_capital: number | null
  created_at: string | null
  updated_at: string | null
}

interface PersonGroup {
  person: string
  alias: string | null
  accounts: Account[]
}

interface AccountsData {
  production: PersonGroup[]
  sandbox: PersonGroup[]
}

interface TestResult {
  account_id: string
  person: string
  success: boolean
  message: string
  tradier_account_number?: string
  total_equity?: number
  option_buying_power?: number
  stock_buying_power?: number
  account_type?: string
  open_positions?: number
  day_pnl?: number
}

/* ── Helpers ───────────────────────────────────────────────────── */

function fmtDollar(n: number | null | undefined): string {
  if (n == null) return '--'
  return '$' + n.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

/* ── Bot badge colors ──────────────────────────────────────────── */

const ALL_BOTS = ['FLAME', 'SPARK', 'INFERNO'] as const

const BOT_COLORS: Record<string, string> = {
  FLAME: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  SPARK: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  INFERNO: 'bg-red-500/20 text-red-400 border-red-500/30',
}

function parseBots(bot: string): string[] {
  if (!bot) return []
  if (bot === 'BOTH') return [...ALL_BOTS]
  return bot.split(',').map(b => b.trim()).filter(Boolean)
}

function serializeBots(bots: string[]): string {
  const sorted = bots
    .filter(b => ALL_BOTS.includes(b as typeof ALL_BOTS[number]))
    .sort((a, b) => ALL_BOTS.indexOf(a as typeof ALL_BOTS[number]) - ALL_BOTS.indexOf(b as typeof ALL_BOTS[number]))
  return Array.from(new Set(sorted)).join(',')
}

/** Trading mode for each bot on a given account type */
function getTradingMode(bot: string, accountType: string): { label: string; cls: string } {
  if (accountType === 'production') {
    return { label: 'MONITOR', cls: 'bg-purple-500/20 text-purple-400 border-purple-500/30' }
  }
  // Sandbox: only FLAME places live orders; SPARK/INFERNO are paper-only
  if (bot === 'FLAME') {
    return { label: 'LIVE', cls: 'bg-green-500/20 text-green-400 border-green-500/30' }
  }
  return { label: 'PAPER', cls: 'bg-gray-500/20 text-gray-400 border-gray-500/30' }
}

function BotBadges({ bot, accountType }: { bot: string; accountType: string }) {
  const bots = parseBots(bot)
  return (
    <div className="flex gap-1 flex-wrap">
      {bots.map(b => {
        const cls = BOT_COLORS[b] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
        const mode = getTradingMode(b, accountType)
        return (
          <span key={b} className="inline-flex items-center gap-1">
            <span className={`text-xs font-medium px-2 py-0.5 rounded-l border ${cls}`}>
              {b}
            </span>
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-r border ${mode.cls}`}>
              {mode.label}
            </span>
          </span>
        )
      })}
    </div>
  )
}

function BotCheckboxes({
  selected,
  onChange,
}: {
  selected: string[]
  onChange: (bots: string[]) => void
}) {
  const toggle = (bot: string) => {
    if (selected.includes(bot)) {
      onChange(selected.filter(b => b !== bot))
    } else {
      onChange([...selected, bot])
    }
  }

  return (
    <div className="flex gap-2 mt-1">
      {ALL_BOTS.map(bot => {
        const isSelected = selected.includes(bot)
        const cls = isSelected
          ? BOT_COLORS[bot]
          : 'bg-gray-800 text-gray-500 border-gray-700'
        return (
          <button
            key={bot}
            type="button"
            onClick={() => toggle(bot)}
            className={`text-xs font-medium px-3 py-1.5 rounded border transition-colors cursor-pointer ${cls}`}
          >
            {bot}
          </button>
        )
      })}
    </div>
  )
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${
        active ? 'bg-green-400' : 'bg-red-400'
      }`}
      title={active ? 'Active' : 'Inactive'}
    />
  )
}

/* ── Add Account Modal ─────────────────────────────────────────── */

function AddAccountModal({
  onClose,
  onSave,
  presetPerson,
  presetType,
}: {
  onClose: () => void
  onSave: (data: {
    person: string
    account_id: string
    api_key: string
    bot: string
    type: string
    capital_pct: number
    pdt_enabled: boolean
  }) => Promise<void>
  /** When set, locks person field to this value (for adding sub-accounts) */
  presetPerson?: string
  /** When set, locks type to this value (e.g. 'production') */
  presetType?: string
}) {
  const [person, setPerson] = useState(presetPerson ?? '')
  const [accountId, setAccountId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [selectedBots, setSelectedBots] = useState<string[]>([...ALL_BOTS])
  const [type, setType] = useState(presetType ?? 'sandbox')
  const [capitalPct, setCapitalPct] = useState(100)
  const [pdtEnabled, setPdtEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const isProduction = type === 'production'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedBots.length === 0) {
      setError('Select at least one bot')
      return
    }
    setError('')
    setSaving(true)
    try {
      await onSave({
        person: presetPerson ?? person,
        account_id: accountId,
        api_key: apiKey,
        bot: serializeBots(selectedBots),
        type: presetType ?? type,
        capital_pct: capitalPct,
        pdt_enabled: isProduction ? false : pdtEnabled,
      })
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const title = presetPerson
    ? `Add Production Account for ${presetPerson}`
    : 'Add Account'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="bg-forge-card border border-amber-900/30 rounded-lg p-6 w-full max-w-md shadow-xl"
      >
        <h2 className="text-lg font-bold text-white mb-4">{title}</h2>

        {error && (
          <div className="mb-3 p-2 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-sm">
            {error}
          </div>
        )}

        {isProduction && (
          <div className="mb-3 p-2 bg-red-500/10 border border-red-500/30 rounded text-red-300 text-xs">
            Production accounts trade with REAL MONEY on Tradier. Orders will be placed automatically.
          </div>
        )}

        <label className="block mb-3">
          <span className="text-sm text-gray-400">Person</span>
          {presetPerson ? (
            <div className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-gray-400 text-sm">
              {presetPerson}
            </div>
          ) : (
            <input
              required
              value={person}
              onChange={(e) => setPerson(e.target.value)}
              className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm focus:border-amber-500 focus:outline-none"
              placeholder="e.g. Matt"
            />
          )}
        </label>

        <label className="block mb-3">
          <span className="text-sm text-gray-400">Tradier Account ID</span>
          <input
            required
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm font-mono focus:border-amber-500 focus:outline-none"
            placeholder="e.g. VA12345678"
          />
        </label>

        <label className="block mb-3">
          <span className="text-sm text-gray-400">API Key</span>
          <input
            required
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm font-mono focus:border-amber-500 focus:outline-none"
            placeholder={isProduction ? 'Tradier production API key' : 'Tradier sandbox API key'}
          />
        </label>

        <div className="mb-3">
          <span className="text-sm text-gray-400">Bot Assignment</span>
          <BotCheckboxes selected={selectedBots} onChange={setSelectedBots} />
        </div>

        {!presetType && (
          <label className="block mb-3">
            <span className="text-sm text-gray-400">Type</span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm focus:border-amber-500 focus:outline-none"
            >
              <option value="sandbox">Sandbox</option>
              <option value="production">Production</option>
            </select>
          </label>
        )}

        <div className="flex gap-3 mb-3">
          <label className="flex-1">
            <span className="text-sm text-gray-400">Capital to Use (%)</span>
              <div className="mt-1 flex items-center gap-2">
                <input
                  type="range"
                  min="1"
                  max="100"
                  value={capitalPct}
                  onChange={(e) => setCapitalPct(parseInt(e.target.value))}
                  className="flex-1 accent-amber-500"
                />
                <span className="text-white text-sm font-mono w-10 text-right">{capitalPct}%</span>
              </div>
            </label>

            <div className="flex-1">
              <span className="text-sm text-gray-400 block">PDT Enforcement</span>
              <button
                type="button"
                onClick={() => setPdtEnabled(!pdtEnabled)}
                className={`mt-1 w-full px-3 py-2 rounded text-sm font-medium border transition-colors ${
                  pdtEnabled
                    ? 'bg-green-500/10 border-green-500/30 text-green-400'
                    : 'bg-gray-500/10 border-gray-600 text-gray-400'
                }`}
              >
                {pdtEnabled ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>

        <div className="flex justify-end gap-3 mt-5">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 text-sm font-medium bg-amber-600 hover:bg-amber-500 text-white rounded transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Add Account'}
          </button>
        </div>
      </form>
    </div>
  )
}

/* ── Edit Account Modal ───────────────────────────────────────── */

function EditAccountModal({
  account,
  onClose,
  onSave,
}: {
  account: Account
  onClose: () => void
  onSave: (id: number, data: {
    bot?: string
    capital_pct?: number
    pdt_enabled?: boolean
  }) => Promise<void>
}) {
  const [selectedBots, setSelectedBots] = useState<string[]>(parseBots(account.bot))
  const [capitalPct, setCapitalPct] = useState(account.capital_pct || 100)
  const [pdtEnabled, setPdtEnabled] = useState(account.pdt_enabled)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const liveBalance = account.live_balance
  const allocatedPreview = liveBalance != null
    ? Math.round(liveBalance * capitalPct / 100)
    : null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedBots.length === 0) {
      setError('Select at least one bot')
      return
    }
    setError('')
    setSaving(true)
    try {
      await onSave(account.id, {
        bot: serializeBots(selectedBots),
        capital_pct: capitalPct,
        pdt_enabled: pdtEnabled,
      })
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="bg-forge-card border border-amber-900/30 rounded-lg p-6 w-full max-w-sm shadow-xl"
      >
        <h2 className="text-lg font-bold text-white mb-1">Edit Account</h2>
        <p className="text-sm text-gray-500 mb-4">
          <span className="font-mono">{account.account_id}</span>
          <span className="mx-2 text-gray-600">|</span>
          {account.person}
        </p>

        {error && (
          <div className="mb-3 p-2 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="mb-4">
          <span className="text-sm text-gray-400">Bot Assignment</span>
          <BotCheckboxes selected={selectedBots} onChange={setSelectedBots} />
        </div>

        {/* Capital % with live preview */}
        <div className="mb-4">
          <span className="text-sm text-gray-400">Capital to Use</span>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="range"
                min="1"
                max="100"
                value={capitalPct}
                onChange={(e) => setCapitalPct(parseInt(e.target.value))}
                className="flex-1 accent-amber-500"
              />
              <span className="text-white text-sm font-mono w-10 text-right">{capitalPct}%</span>
            </div>
            {liveBalance != null && (
              <div className="mt-2 p-2 bg-forge-bg rounded border border-gray-700/50">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Account Balance</span>
                  <span className="text-white font-mono">{fmtDollar(liveBalance)}</span>
                </div>
                <div className="flex justify-between text-xs mt-1">
                  <span className="text-gray-500">{capitalPct}% Allocated</span>
                  <span className="text-amber-400 font-mono font-medium">{fmtDollar(allocatedPreview)}</span>
                </div>
              </div>
            )}
          </div>

        <div className="mb-4">
          <span className="text-sm text-gray-400 block mb-1">PDT Enforcement</span>
          <button
            type="button"
            onClick={() => setPdtEnabled(!pdtEnabled)}
            className={`px-4 py-2 rounded text-sm font-medium border transition-colors ${
              pdtEnabled
                ? 'bg-green-500/10 border-green-500/30 text-green-400'
                : 'bg-gray-500/10 border-gray-600 text-gray-400'
            }`}
          >
            {pdtEnabled ? 'ON — 4 day trades / 5 days' : 'OFF — No PDT limit'}
          </button>
        </div>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 text-sm font-medium bg-amber-600 hover:bg-amber-500 text-white rounded transition-colors disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </form>
    </div>
  )
}

/* ── Person-first data structure ───────────────────────────────── */

interface PersonView {
  person: string
  alias: string | null
  sandbox: Account | null
  production: Account[]
}

/** Merge API response into person-first view */
function buildPersonViews(data: AccountsData): PersonView[] {
  const map = new Map<string, PersonView>()

  for (const group of data.sandbox) {
    const view: PersonView = { person: group.person, alias: group.alias ?? null, sandbox: group.accounts[0] ?? null, production: [] }
    map.set(group.person, view)
  }
  for (const group of data.production) {
    const existing = map.get(group.person)
    if (existing) {
      existing.production = group.accounts
      // Use alias from whichever group has it
      if (!existing.alias && group.alias) existing.alias = group.alias
    } else {
      map.set(group.person, { person: group.person, alias: group.alias ?? null, sandbox: null, production: group.accounts })
    }
  }

  // Sort by person name
  return Array.from(map.values()).sort((a, b) => a.person.localeCompare(b.person))
}

/* ── Main Page ─────────────────────────────────────────────────── */

export default function AccountsContent() {
  const [data, setData] = useState<AccountsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [addPresetPerson, setAddPresetPerson] = useState<string | undefined>()
  const [addPresetType, setAddPresetType] = useState<string | undefined>()
  const [editAccount, setEditAccount] = useState<Account | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [testingAll, setTestingAll] = useState(false)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [editingAlias, setEditingAlias] = useState<string | null>(null)
  const [aliasInput, setAliasInput] = useState('')

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch('/api/accounts/manage')
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const json = await res.json()
      setData(json)
      setError('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load accounts')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAccounts()
  }, [fetchAccounts])

  /* ── Alias editing ────────────────────────────────────────── */

  const saveAlias = async (person: string, alias: string) => {
    try {
      const res = await fetch('/api/persons/alias', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ person, alias: alias.trim() || null }),
      })
      if (!res.ok) throw new Error(`${res.status}`)
      setEditingAlias(null)
      await fetchAccounts()
    } catch {
      // Silently fail — user can retry
      setEditingAlias(null)
    }
  }

  /* ── CRUD handlers ─────────────────────────────────────────── */

  const handleCreate = async (body: {
    person: string
    account_id: string
    api_key: string
    bot: string
    type: string
    capital_pct: number
    pdt_enabled: boolean
  }) => {
    const res = await fetch('/api/accounts/manage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      throw new Error(j.error || j.detail || `${res.status}`)
    }
    await fetchAccounts()
  }

  const handleUpdate = async (
    id: number,
    body: { bot?: string; is_active?: boolean; capital_pct?: number; pdt_enabled?: boolean },
  ) => {
    const res = await fetch(`/api/accounts/manage/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      throw new Error(j.error || j.detail || `${res.status}`)
    }
    await fetchAccounts()
  }

  const handleDeactivate = async (id: number, accountId: string) => {
    if (!confirm(`Deactivate account ${accountId}? This is a soft delete.`)) return
    const res = await fetch(`/api/accounts/manage/${id}`, { method: 'DELETE' })
    if (!res.ok) {
      const j = await res.json().catch(() => ({}))
      alert(j.error || j.detail || 'Failed to deactivate')
      return
    }
    await fetchAccounts()
  }

  const handleReactivate = async (id: number) => {
    await handleUpdate(id, { is_active: true })
  }

  /* ── Connectivity tests ────────────────────────────────────── */

  const handleTestAll = async () => {
    if (!data) return
    setTestingAll(true)
    setTestResults({})

    try {
      const res = await fetch('/api/accounts/test-all', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to test accounts')
      const results: TestResult[] = await res.json()

      const map: Record<string, TestResult> = {}
      for (const r of results) {
        map[r.account_id] = r
      }
      setTestResults(map)
    } catch {
      setTestResults({})
    } finally {
      setTestingAll(false)
    }
  }

  const handleTestOne = async (acct: Account) => {
    setTestingId(acct.id)
    try {
      const res = await fetch(`/api/accounts/manage/${acct.id}/test`, { method: 'POST' })
      if (!res.ok) throw new Error('Test failed')
      const result: TestResult = await res.json()
      setTestResults(prev => ({ ...prev, [acct.account_id]: result }))
    } catch {
      setTestResults(prev => ({
        ...prev,
        [acct.account_id]: {
          account_id: acct.account_id,
          person: acct.person,
          success: false,
          message: 'Test request failed',
        },
      }))
    } finally {
      setTestingId(null)
    }
  }

  /* ── Open add modal with optional presets ───────────────────── */

  const openAddModal = (presetPerson?: string, presetType?: string) => {
    setAddPresetPerson(presetPerson)
    setAddPresetType(presetType)
    setShowAdd(true)
  }

  const closeAddModal = () => {
    setShowAdd(false)
    setAddPresetPerson(undefined)
    setAddPresetType(undefined)
  }

  /* ── Render ────────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-white">Accounts</h1>
        <div className="animate-pulse space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-forge-card rounded-lg skeleton-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-white">Accounts</h1>
        <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p className="text-red-400 text-sm">{error}</p>
          <button
            onClick={() => { setLoading(true); fetchAccounts() }}
            className="mt-2 text-xs text-amber-400 hover:text-amber-300"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  const personViews = data ? buildPersonViews(data) : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Accounts</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage Tradier sandbox and production accounts
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleTestAll}
            disabled={testingAll}
            className="px-3 py-1.5 text-sm border border-gray-600 text-gray-300 hover:text-white hover:border-gray-400 rounded transition-colors disabled:opacity-50"
          >
            {testingAll ? 'Testing...' : 'Test All'}
          </button>
          <button
            onClick={() => openAddModal()}
            className="px-3 py-1.5 text-sm font-medium bg-amber-600 hover:bg-amber-500 text-white rounded transition-colors"
          >
            + Add Account
          </button>
        </div>
      </div>

      {/* Person-first layout */}
      {personViews.length > 0 ? (
        <div className="space-y-4">
          {personViews.map((pv) => (
            <div
              key={pv.person}
              className="bg-forge-card border border-gray-800 rounded-lg overflow-hidden"
            >
              {/* Person header with alias editing */}
              <div className="px-4 py-3 border-b border-gray-800">
                {editingAlias === pv.person ? (
                  <div className="flex items-center gap-2">
                    <input
                      autoFocus
                      type="text"
                      value={aliasInput}
                      onChange={(e) => setAliasInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveAlias(pv.person, aliasInput)
                        if (e.key === 'Escape') setEditingAlias(null)
                      }}
                      onBlur={() => saveAlias(pv.person, aliasInput)}
                      placeholder={pv.person}
                      className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-white text-lg font-medium focus:border-amber-500 focus:outline-none w-48"
                    />
                    <span className="text-gray-500 text-sm">Press Enter to save, Esc to cancel</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <h3 className="text-white font-medium text-lg">
                      {pv.alias || pv.person}
                      {pv.alias && <span className="text-gray-500 text-sm font-normal ml-2">({pv.person})</span>}
                    </h3>
                    <button
                      onClick={() => { setEditingAlias(pv.person); setAliasInput(pv.alias || '') }}
                      className="text-gray-500 hover:text-amber-400 transition-colors"
                      title="Edit display name"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                        <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
                      </svg>
                    </button>
                  </div>
                )}
              </div>

              {/* Sandbox section */}
              <div className="px-4 pt-3 pb-1">
                <h4 className="text-xs font-medium text-blue-400 uppercase tracking-wider mb-2">
                  Sandbox
                </h4>
              </div>
              {pv.sandbox ? (
                <div className="border-b border-gray-800/50">
                  <AccountCard
                    account={pv.sandbox}
                    testResult={testResults[pv.sandbox.account_id]}
                    testingId={testingId}
                    onEdit={() => setEditAccount(pv.sandbox!)}
                    onDeactivate={() => handleDeactivate(pv.sandbox!.id, pv.sandbox!.account_id)}
                    onReactivate={() => handleReactivate(pv.sandbox!.id)}
                    onTest={() => handleTestOne(pv.sandbox!)}
                  />
                </div>
              ) : (
                <div className="px-4 pb-3 text-xs text-gray-600">
                  No sandbox account
                </div>
              )}

              {/* Production section */}
              <div className="px-4 pt-3 pb-1">
                <h4 className="text-xs font-medium text-purple-400 uppercase tracking-wider mb-2">
                  Production
                </h4>
              </div>
              {pv.production.length > 0 ? (
                <div className="divide-y divide-gray-800/50">
                  {pv.production.map((acct) => (
                    <AccountCard
                      key={acct.id}
                      account={acct}
                      testResult={testResults[acct.account_id]}
                      testingId={testingId}
                      onEdit={() => setEditAccount(acct)}
                      onDeactivate={() => handleDeactivate(acct.id, acct.account_id)}
                      onReactivate={() => handleReactivate(acct.id)}
                      onTest={() => handleTestOne(acct)}
                    />
                  ))}
                </div>
              ) : (
                <div className="px-4 pb-1 text-xs text-gray-600">
                  No production accounts
                </div>
              )}

              {/* Add production sub-account button */}
              <div className="px-4 py-3">
                <button
                  onClick={() => openAddModal(pv.person, 'production')}
                  className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
                >
                  + Add Production Account
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No accounts configured</p>
          <p className="text-sm">Add a Tradier account to get started.</p>
        </div>
      )}

      {/* Modals */}
      {showAdd && (
        <AddAccountModal
          onClose={closeAddModal}
          onSave={handleCreate}
          presetPerson={addPresetPerson}
          presetType={addPresetType}
        />
      )}
      {editAccount && (
        <EditAccountModal
          account={editAccount}
          onClose={() => setEditAccount(null)}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}

/* ── Account Card ────────────────────────────────────────────── */

function AccountCard({
  account,
  testResult,
  testingId,
  onEdit,
  onDeactivate,
  onReactivate,
  onTest,
}: {
  account: Account
  testResult?: TestResult
  testingId?: number | null
  onEdit: () => void
  onDeactivate: () => void
  onReactivate: () => void
  onTest: () => void
}) {
  const isTesting = testingId === account.id
  return (
    <div className="px-4 py-3">
      {/* Top row: status, account ID, bots, PDT, actions */}
      <div className="flex items-center gap-3">
        <StatusDot active={account.is_active} />
        <span className="font-mono text-sm text-white">{account.account_id}</span>
        <span className="hidden sm:inline font-mono text-xs text-gray-600">{account.api_key_masked}</span>
        <BotBadges bot={account.bot} accountType={account.type} />
        <span
          className={`text-xs px-1.5 py-0.5 rounded ${
            account.pdt_enabled
              ? 'bg-green-500/10 text-green-400 border border-green-500/20'
              : 'bg-gray-500/10 text-gray-500 border border-gray-600'
          }`}
        >
          PDT {account.pdt_enabled ? 'ON' : 'OFF'}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={onTest}
            disabled={isTesting}
            className="p-1.5 text-gray-500 hover:text-blue-400 transition-colors disabled:opacity-50"
            title="Test Connection"
          >
            {isTesting ? (
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" className="animate-spin">
                <path d="M8 0a8 8 0 100 16A8 8 0 008 0zm0 14A6 6 0 118 2a6 6 0 010 12z" opacity="0.3" />
                <path d="M8 0a8 8 0 018 8h-2A6 6 0 008 2V0z" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0a8 8 0 100 16A8 8 0 008 0zm3.28 5.78l-4 4a.75.75 0 01-1.06 0l-2-2a.75.75 0 011.06-1.06L6.75 8.19l3.47-3.47a.75.75 0 011.06 1.06z" />
              </svg>
            )}
          </button>
          <button onClick={onEdit} className="p-1.5 text-gray-500 hover:text-amber-400 transition-colors" title="Edit">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M11.013 1.427a1.75 1.75 0 012.474 0l1.086 1.086a1.75 1.75 0 010 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 01-.927-.928l.929-3.25a1.75 1.75 0 01.445-.758l8.61-8.61zm1.414 1.06a.25.25 0 00-.354 0L3.463 11.098a.25.25 0 00-.064.108l-.563 1.97 1.971-.564a.25.25 0 00.108-.064l8.61-8.61a.25.25 0 000-.354L12.427 2.487z" />
            </svg>
          </button>
          {account.is_active ? (
            <button onClick={onDeactivate} className="p-1.5 text-gray-500 hover:text-red-400 transition-colors" title="Deactivate">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
              </svg>
            </button>
          ) : (
            <button onClick={onReactivate} className="p-1.5 text-gray-500 hover:text-green-400 transition-colors" title="Reactivate">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Bottom row: live balance, capital %, allocated amount */}
      <div className="mt-2 flex items-center gap-4 text-xs">
        {account.live_balance != null ? (
          <>
            <div>
              <span className="text-gray-500">Balance: </span>
              <span className="text-white font-mono">{fmtDollar(account.live_balance)}</span>
            </div>
            <div>
              <span className="text-gray-500">OBP: </span>
              <span className="text-white font-mono">{fmtDollar(account.live_buying_power)}</span>
            </div>
            <div>
              <span className="text-gray-500">Capital: </span>
              <span className="text-amber-400 font-mono font-medium">
                {account.capital_pct}% = {fmtDollar(account.allocated_capital)}
              </span>
            </div>
            {account.type === 'production' && (
              <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">LIVE</span>
            )}
            {account.open_positions > 0 && (
              <div>
                <span className="text-gray-500">Positions: </span>
                <span className="text-white font-mono">{account.open_positions}</span>
              </div>
            )}
          </>
        ) : (
          <span className="text-gray-600">Balance unavailable — Tradier unreachable</span>
        )}
      </div>

      {/* Test result details (shown after clicking Test All) */}
      {testResult && (
        <div className="mt-2 p-2 rounded border border-gray-700/50 bg-forge-bg">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs font-medium ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
              {testResult.success ? 'Connected' : `Failed: ${testResult.message}`}
            </span>
            {testResult.tradier_account_number && (
              <span className="text-xs text-gray-500 font-mono">#{testResult.tradier_account_number}</span>
            )}
            {testResult.account_type && (
              <span className="text-xs text-gray-500">{testResult.account_type}</span>
            )}
          </div>
          {testResult.success && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-xs">
              <div>
                <span className="text-gray-500">Equity: </span>
                <span className="text-white font-mono">{fmtDollar(testResult.total_equity)}</span>
              </div>
              <div>
                <span className="text-gray-500">Option BP: </span>
                <span className="text-white font-mono">{fmtDollar(testResult.option_buying_power)}</span>
              </div>
              <div>
                <span className="text-gray-500">Stock BP: </span>
                <span className="text-white font-mono">{fmtDollar(testResult.stock_buying_power)}</span>
              </div>
              <div>
                <span className="text-gray-500">Day P&L: </span>
                <span className={`font-mono ${(testResult.day_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {fmtDollar(testResult.day_pnl)}
                </span>
              </div>
              {(testResult.open_positions ?? 0) > 0 && (
                <div>
                  <span className="text-gray-500">Positions: </span>
                  <span className="text-white font-mono">{testResult.open_positions}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
