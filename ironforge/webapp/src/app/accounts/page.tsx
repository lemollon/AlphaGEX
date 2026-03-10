'use client'

import { useState, useEffect, useCallback } from 'react'

/* ── Types ─────────────────────────────────────────────────────── */

interface Account {
  id: number
  account_id: string
  api_key_masked: string
  bot: string
  type: string
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

interface PersonGroup {
  person: string
  accounts: Account[]
}

interface SandboxAccount extends Account {
  person: string
}

interface AccountsData {
  production: PersonGroup[]
  sandbox: SandboxAccount | null
}

interface TestResult {
  account_id: string
  success: boolean
  message: string
}

/* ── Bot badge colors ──────────────────────────────────────────── */

const BOT_COLORS: Record<string, string> = {
  FLAME: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  SPARK: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  INFERNO: 'bg-red-500/20 text-red-400 border-red-500/30',
  BOTH: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
}

function BotBadge({ bot }: { bot: string }) {
  const cls = BOT_COLORS[bot] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
  return (
    <span className={`text-xs font-medium px-2 py-0.5 rounded border ${cls}`}>
      {bot}
    </span>
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
}: {
  onClose: () => void
  onSave: (data: { person: string; account_id: string; api_key: string; bot: string; type: string }) => Promise<void>
}) {
  const [person, setPerson] = useState('')
  const [accountId, setAccountId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [bot, setBot] = useState('BOTH')
  const [type, setType] = useState('production')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSaving(true)
    try {
      await onSave({ person, account_id: accountId, api_key: apiKey, bot, type })
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
        className="bg-forge-card border border-amber-900/30 rounded-lg p-6 w-full max-w-md shadow-xl"
      >
        <h2 className="text-lg font-bold text-white mb-4">Add Account</h2>

        {error && (
          <div className="mb-3 p-2 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-sm">
            {error}
          </div>
        )}

        <label className="block mb-3">
          <span className="text-sm text-gray-400">Person</span>
          <input
            required
            value={person}
            onChange={(e) => setPerson(e.target.value)}
            className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm focus:border-amber-500 focus:outline-none"
            placeholder="e.g. Matt"
          />
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
            placeholder="Tradier sandbox API key"
          />
        </label>

        <div className="flex gap-3 mb-3">
          <label className="flex-1">
            <span className="text-sm text-gray-400">Bot Assignment</span>
            <select
              value={bot}
              onChange={(e) => setBot(e.target.value)}
              className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm focus:border-amber-500 focus:outline-none"
            >
              <option value="BOTH">BOTH</option>
              <option value="FLAME">FLAME</option>
              <option value="SPARK">SPARK</option>
              <option value="INFERNO">INFERNO</option>
            </select>
          </label>

          <label className="flex-1">
            <span className="text-sm text-gray-400">Type</span>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm focus:border-amber-500 focus:outline-none"
            >
              <option value="production">Production</option>
              <option value="sandbox">Sandbox</option>
            </select>
          </label>
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

/* ── Edit Bot Modal ────────────────────────────────────────────── */

function EditBotModal({
  account,
  onClose,
  onSave,
}: {
  account: Account & { person?: string }
  onClose: () => void
  onSave: (id: number, data: { bot?: string; is_active?: boolean }) => Promise<void>
}) {
  const [bot, setBot] = useState(account.bot)
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onSave(account.id, { bot })
      onClose()
    } catch {
      // error handled in parent
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
        <h2 className="text-lg font-bold text-white mb-1">Edit Bot Assignment</h2>
        <p className="text-sm text-gray-500 mb-4 font-mono">{account.account_id}</p>

        <label className="block mb-4">
          <span className="text-sm text-gray-400">Bot</span>
          <select
            value={bot}
            onChange={(e) => setBot(e.target.value)}
            className="mt-1 w-full bg-forge-bg border border-gray-700 rounded px-3 py-2 text-white text-sm focus:border-amber-500 focus:outline-none"
          >
            <option value="BOTH">BOTH</option>
            <option value="FLAME">FLAME</option>
            <option value="SPARK">SPARK</option>
            <option value="INFERNO">INFERNO</option>
          </select>
        </label>

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

/* ── Main Page ─────────────────────────────────────────────────── */

export default function AccountsPage() {
  const [data, setData] = useState<AccountsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [editAccount, setEditAccount] = useState<(Account & { person?: string }) | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [testingAll, setTestingAll] = useState(false)

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

  /* ── CRUD handlers ─────────────────────────────────────────── */

  const handleCreate = async (body: {
    person: string
    account_id: string
    api_key: string
    bot: string
    type: string
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

  const handleUpdate = async (id: number, body: { bot?: string; is_active?: boolean }) => {
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

  /* ── Connectivity test ─────────────────────────────────────── */

  const handleTestAll = async () => {
    if (!data) return
    setTestingAll(true)
    setTestResults({})

    try {
      // Server-side endpoint reads real API keys from Databricks and tests each
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

  const allAccounts: (Account & { person: string })[] = []
  if (data) {
    for (const group of data.production) {
      for (const acct of group.accounts) {
        allAccounts.push({ ...acct, person: group.person })
      }
    }
    if (data.sandbox) {
      allAccounts.push(data.sandbox)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Accounts</h1>
          <p className="text-sm text-gray-500 mt-1">
            Tradier sandbox accounts receiving mirrored trades
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
            onClick={() => setShowAdd(true)}
            className="px-3 py-1.5 text-sm font-medium bg-amber-600 hover:bg-amber-500 text-white rounded transition-colors"
          >
            + Add Account
          </button>
        </div>
      </div>

      {/* Production Accounts */}
      {data && data.production.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
            Production Accounts
          </h2>
          <div className="space-y-3">
            {data.production.map((group) => (
              <div
                key={group.person}
                className="bg-forge-card border border-amber-900/20 rounded-lg overflow-hidden"
              >
                <div className="px-4 py-3 border-b border-amber-900/10">
                  <h3 className="text-white font-medium">{group.person}</h3>
                </div>
                <div className="divide-y divide-gray-800/50">
                  {group.accounts.map((acct) => (
                    <AccountRow
                      key={acct.id}
                      account={acct}
                      person={group.person}
                      testResult={testResults[acct.account_id]}
                      onEdit={() => setEditAccount({ ...acct, person: group.person })}
                      onDeactivate={() => handleDeactivate(acct.id, acct.account_id)}
                      onReactivate={() => handleReactivate(acct.id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Sandbox Account */}
      {data && data.sandbox && (
        <section>
          <h2 className="text-sm font-medium text-gray-400 uppercase tracking-wider mb-3">
            Sandbox Account
          </h2>
          <div className="bg-forge-card border border-blue-900/20 rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-blue-900/10">
              <div className="flex items-center gap-2">
                <h3 className="text-white font-medium">{data.sandbox.person}</h3>
                <span className="text-xs text-blue-400 bg-blue-500/10 border border-blue-500/20 px-1.5 py-0.5 rounded">
                  sandbox
                </span>
              </div>
            </div>
            <AccountRow
              account={data.sandbox}
              person={data.sandbox.person}
              testResult={testResults[data.sandbox.account_id]}
              onEdit={() => setEditAccount(data.sandbox!)}
              onDeactivate={() => handleDeactivate(data.sandbox!.id, data.sandbox!.account_id)}
              onReactivate={() => handleReactivate(data.sandbox!.id)}
            />
          </div>
        </section>
      )}

      {/* Empty state */}
      {data && data.production.length === 0 && !data.sandbox && (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">No accounts configured</p>
          <p className="text-sm">Add a Tradier sandbox account to start mirroring trades.</p>
        </div>
      )}

      {/* Modals */}
      {showAdd && (
        <AddAccountModal onClose={() => setShowAdd(false)} onSave={handleCreate} />
      )}
      {editAccount && (
        <EditBotModal
          account={editAccount}
          onClose={() => setEditAccount(null)}
          onSave={handleUpdate}
        />
      )}
    </div>
  )
}

/* ── Account Row ─────────────────────────────────────────────── */

function AccountRow({
  account,
  person,
  testResult,
  onEdit,
  onDeactivate,
  onReactivate,
}: {
  account: Account
  person: string
  testResult?: TestResult
  onEdit: () => void
  onDeactivate: () => void
  onReactivate: () => void
}) {
  return (
    <div className="px-4 py-3 flex items-center gap-4">
      {/* Status + Account ID */}
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <StatusDot active={account.is_active} />
        <span className="font-mono text-sm text-white truncate">{account.account_id}</span>
      </div>

      {/* API Key (masked) */}
      <div className="hidden sm:block">
        <span className="font-mono text-xs text-gray-500">{account.api_key_masked}</span>
      </div>

      {/* Bot badge */}
      <BotBadge bot={account.bot} />

      {/* Test result */}
      {testResult && (
        <span
          className={`text-xs ${
            testResult.success ? 'text-green-400' : 'text-red-400'
          }`}
          title={testResult.message}
        >
          {testResult.success ? 'Connected' : 'Failed'}
        </span>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1">
        <button
          onClick={onEdit}
          className="p-1.5 text-gray-500 hover:text-amber-400 transition-colors"
          title="Edit bot assignment"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M11.013 1.427a1.75 1.75 0 012.474 0l1.086 1.086a1.75 1.75 0 010 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 01-.927-.928l.929-3.25a1.75 1.75 0 01.445-.758l8.61-8.61zm1.414 1.06a.25.25 0 00-.354 0L3.463 11.098a.25.25 0 00-.064.108l-.563 1.97 1.971-.564a.25.25 0 00.108-.064l8.61-8.61a.25.25 0 000-.354L12.427 2.487z" />
          </svg>
        </button>
        {account.is_active ? (
          <button
            onClick={onDeactivate}
            className="p-1.5 text-gray-500 hover:text-red-400 transition-colors"
            title="Deactivate"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
            </svg>
          </button>
        ) : (
          <button
            onClick={onReactivate}
            className="p-1.5 text-gray-500 hover:text-green-400 transition-colors"
            title="Reactivate"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
              <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
