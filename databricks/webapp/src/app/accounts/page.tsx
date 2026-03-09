'use client'

import { useState } from 'react'
import useSWR from 'swr'
import { fetcher } from '@/lib/fetcher'
import PasswordGate from '@/components/PasswordGate'

interface Account {
  account_id: string
  api_key: string
  api_key_full: string
  owner_name: string
  bot_name: string
  is_active: boolean
  notes: string | null
  created_at: string | null
}

const BOT_OPTIONS = ['FLAME', 'SPARK', 'BOTH'] as const

export default function AccountsPage() {
  return (
    <PasswordGate>
      <AccountsContent />
    </PasswordGate>
  )
}

function AccountsContent() {
  const { data, mutate } = useSWR<{ accounts: Account[] }>('/api/accounts', fetcher, {
    refreshInterval: 30_000,
  })
  const accounts = data?.accounts || []

  const [showAdd, setShowAdd] = useState(false)
  const [editId, setEditId] = useState<string | null>(null)
  const [testing, setTesting] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<Record<string, { valid: boolean; message: string }>>({})
  const [actionError, setActionError] = useState<string | null>(null)

  async function handleTest(accountId: string) {
    setTesting(accountId)
    setTestResult((prev) => ({ ...prev, [accountId]: undefined as any }))
    try {
      const res = await fetch(`/api/accounts/${accountId}/test`, { method: 'POST' })
      const data = await res.json()
      setTestResult((prev) => ({ ...prev, [accountId]: data }))
    } catch {
      setTestResult((prev) => ({ ...prev, [accountId]: { valid: false, message: 'Request failed' } }))
    } finally {
      setTesting(null)
    }
  }

  async function handleDeactivate(accountId: string) {
    if (!confirm('Deactivate this account? The scanner will stop mirroring orders to it.')) return
    setActionError(null)
    try {
      await fetch(`/api/accounts/${accountId}`, { method: 'DELETE' })
      mutate()
    } catch (err: any) {
      setActionError(err.message)
    }
  }

  async function handleReactivate(accountId: string) {
    setActionError(null)
    try {
      await fetch(`/api/accounts/${accountId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: true }),
      })
      mutate()
    } catch (err: any) {
      setActionError(err.message)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Sandbox Accounts</h1>
        <button
          onClick={() => { setShowAdd(true); setEditId(null) }}
          className="px-4 py-2 text-sm font-medium bg-amber-600 hover:bg-amber-500 text-white rounded-lg transition-colors"
        >
          + Add Account
        </button>
      </div>

      {actionError && (
        <div className="rounded-lg bg-red-500/15 border border-red-500/30 px-4 py-2 text-sm text-red-400">
          {actionError}
        </div>
      )}

      {/* Account list */}
      <div className="space-y-3">
        {accounts.length === 0 && (
          <div className="rounded-xl border border-forge-border bg-forge-card p-8 text-center text-forge-muted">
            No accounts configured. Add one to get started.
          </div>
        )}
        {accounts.map((acct) => (
          <div
            key={acct.account_id}
            className={`rounded-xl border bg-forge-card p-4 ${
              acct.is_active ? 'border-forge-border' : 'border-red-500/20 opacity-60'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-white font-semibold">{acct.owner_name}</span>
                    <span className="text-xs px-2 py-0.5 rounded bg-forge-border text-forge-muted">
                      {acct.account_id}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        acct.bot_name === 'FLAME'
                          ? 'bg-amber-500/20 text-amber-400'
                          : acct.bot_name === 'SPARK'
                            ? 'bg-blue-500/20 text-blue-400'
                            : 'bg-purple-500/20 text-purple-400'
                      }`}
                    >
                      {acct.bot_name}
                    </span>
                    {acct.is_active ? (
                      <span className="w-2 h-2 rounded-full bg-emerald-500" title="Active" />
                    ) : (
                      <span className="text-xs text-red-400">Inactive</span>
                    )}
                  </div>
                  <div className="text-xs text-forge-muted mt-1 font-mono">{acct.api_key}</div>
                  {acct.notes && <div className="text-xs text-forge-muted mt-0.5">{acct.notes}</div>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {testResult[acct.account_id] && (
                  <span
                    className={`text-xs ${testResult[acct.account_id].valid ? 'text-emerald-400' : 'text-red-400'}`}
                  >
                    {testResult[acct.account_id].valid ? '\u2713' : '\u2717'}{' '}
                    {testResult[acct.account_id].message}
                  </span>
                )}
                <button
                  onClick={() => handleTest(acct.account_id)}
                  disabled={testing === acct.account_id}
                  className="px-3 py-1.5 text-xs rounded border border-forge-border text-forge-muted hover:text-white hover:border-forge-muted transition-colors disabled:opacity-50"
                >
                  {testing === acct.account_id ? 'Testing...' : 'Test'}
                </button>
                <button
                  onClick={() => { setEditId(acct.account_id); setShowAdd(false) }}
                  className="px-3 py-1.5 text-xs rounded border border-forge-border text-forge-muted hover:text-white hover:border-forge-muted transition-colors"
                >
                  Edit
                </button>
                {acct.is_active ? (
                  <button
                    onClick={() => handleDeactivate(acct.account_id)}
                    className="px-3 py-1.5 text-xs rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors"
                  >
                    Deactivate
                  </button>
                ) : (
                  <button
                    onClick={() => handleReactivate(acct.account_id)}
                    className="px-3 py-1.5 text-xs rounded border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 transition-colors"
                  >
                    Reactivate
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Add Account Form */}
      {showAdd && (
        <AccountForm
          onClose={() => setShowAdd(false)}
          onSaved={() => { setShowAdd(false); mutate() }}
        />
      )}

      {/* Edit Account Form */}
      {editId && (
        <AccountForm
          account={accounts.find((a) => a.account_id === editId)}
          onClose={() => setEditId(null)}
          onSaved={() => { setEditId(null); mutate() }}
        />
      )}
    </div>
  )
}

function AccountForm({
  account,
  onClose,
  onSaved,
}: {
  account?: Account
  onClose: () => void
  onSaved: () => void
}) {
  const isEdit = !!account
  const [form, setForm] = useState({
    account_id: account?.account_id || '',
    api_key: account?.api_key_full || '',
    owner_name: account?.owner_name || '',
    bot_name: account?.bot_name || 'BOTH',
    notes: account?.notes || '',
  })
  const [saving, setSaving] = useState(false)
  const [testRes, setTestRes] = useState<{ valid: boolean; message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)

  const valid =
    form.account_id.startsWith('VA') && form.api_key.length > 0 && form.owner_name.length > 0

  async function handleTestKey() {
    if (!form.api_key) return
    setTestRes(null)
    try {
      const res = await fetch('https://sandbox.tradier.com/v1/user/profile', {
        headers: { Authorization: `Bearer ${form.api_key}`, Accept: 'application/json' },
      })
      if (!res.ok) {
        setTestRes({ valid: false, message: `HTTP ${res.status}` })
        return
      }
      const data = await res.json()
      let acct = data.profile?.account
      if (Array.isArray(acct)) acct = acct[0]
      setTestRes({
        valid: true,
        message: `Connected \u2014 account ${acct?.account_number || 'unknown'}`,
      })
    } catch {
      setTestRes({ valid: false, message: 'Connection failed' })
    }
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      if (isEdit) {
        const res = await fetch(`/api/accounts/${account!.account_id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            api_key: form.api_key,
            owner_name: form.owner_name,
            bot_name: form.bot_name,
            notes: form.notes || null,
          }),
        })
        if (!res.ok) {
          const data = await res.json()
          throw new Error(data.error || 'Update failed')
        }
      } else {
        const res = await fetch('/api/accounts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        })
        if (!res.ok) {
          const data = await res.json()
          throw new Error(data.error || 'Create failed')
        }
      }
      onSaved()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-amber-500/30 bg-forge-card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">
          {isEdit ? `Edit ${account!.owner_name}` : 'Add Account'}
        </h2>
        <button onClick={onClose} className="text-forge-muted hover:text-white text-lg">
          &times;
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded px-3 py-2">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-forge-muted mb-1">Account ID</label>
          <input
            value={form.account_id}
            onChange={(e) => setForm((f) => ({ ...f, account_id: e.target.value }))}
            disabled={isEdit}
            placeholder="VA..."
            className="w-full bg-forge-bg border border-forge-border rounded px-3 py-2 text-sm text-white placeholder-forge-muted disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-xs text-forge-muted mb-1">Owner Name</label>
          <input
            value={form.owner_name}
            onChange={(e) => setForm((f) => ({ ...f, owner_name: e.target.value }))}
            placeholder="Name"
            className="w-full bg-forge-bg border border-forge-border rounded px-3 py-2 text-sm text-white placeholder-forge-muted"
          />
        </div>
        <div className="col-span-2">
          <label className="block text-xs text-forge-muted mb-1">API Key</label>
          <div className="flex gap-2">
            <input
              value={form.api_key}
              onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
              type={showKey ? 'text' : 'password'}
              className="flex-1 bg-forge-bg border border-forge-border rounded px-3 py-2 text-sm text-white font-mono"
            />
            <button
              onClick={() => setShowKey(!showKey)}
              className="px-3 py-2 text-xs border border-forge-border rounded text-forge-muted hover:text-white transition-colors"
            >
              {showKey ? 'Hide' : 'Show'}
            </button>
            <button
              onClick={handleTestKey}
              className="px-3 py-2 text-xs border border-forge-border rounded text-forge-muted hover:text-white transition-colors"
            >
              Test
            </button>
          </div>
          {testRes && (
            <div className={`text-xs mt-1 ${testRes.valid ? 'text-emerald-400' : 'text-red-400'}`}>
              {testRes.valid ? '\u2713' : '\u2717'} {testRes.message}
            </div>
          )}
        </div>
        <div>
          <label className="block text-xs text-forge-muted mb-1">Bot Assignment</label>
          <select
            value={form.bot_name}
            onChange={(e) => setForm((f) => ({ ...f, bot_name: e.target.value }))}
            className="w-full bg-forge-bg border border-forge-border rounded px-3 py-2 text-sm text-white"
          >
            {BOT_OPTIONS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-forge-muted mb-1">Notes</label>
          <input
            value={form.notes}
            onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            placeholder="Optional"
            className="w-full bg-forge-bg border border-forge-border rounded px-3 py-2 text-sm text-white placeholder-forge-muted"
          />
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm rounded border border-forge-border text-forge-muted hover:text-white transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={!valid || saving}
          className="px-4 py-2 text-sm rounded bg-amber-600 hover:bg-amber-500 text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving...' : isEdit ? 'Update' : 'Save'}
        </button>
      </div>
    </div>
  )
}
