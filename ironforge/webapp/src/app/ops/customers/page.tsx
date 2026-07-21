'use client'

import { useState } from 'react'
import useSWR, { mutate } from 'swr'
import { fetcher } from '@/lib/fetcher'

/**
 * Operator-only customer admin. Create customer profiles, then map each to the
 * live bot(s) they own. A profile with no bot mapping lands on the Live empty
 * state — mapping it to spark / spark2 is what surfaces that customer's own
 * account. Gated by the operator session server-side (/api/ops/customers).
 */

const KEY = '/api/ops/customers'

interface BotOpt { id: string; label: string }
interface Customer {
  id: string
  email: string
  name: string
  status: string
  emailVerified: boolean
  createdAt: string
  bots: string[]
}
interface ListResp {
  ok: boolean
  error?: string
  bots: BotOpt[]
  customers: Customer[]
}

const input =
  'w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-amber-500 focus:outline-none'
const btn =
  'rounded-md bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-500 disabled:opacity-50'

export default function OpsCustomersPage() {
  const { data, error, isLoading } = useSWR<ListResp>(KEY, fetcher)

  const [form, setForm] = useState({ email: '', firstName: '', lastName: '', phone: '', state: '', password: '' })
  const [creating, setCreating] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  async function createProfile(e: React.FormEvent) {
    e.preventDefault()
    setCreating(true)
    setMsg(null)
    try {
      const res = await fetch(KEY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'create', ...form }),
      })
      const j = await res.json()
      if (!res.ok || !j.ok) {
        const detail = j.fields ? Object.values(j.fields).join(' ') : ''
        throw new Error(`${j.error ?? 'Failed to create profile.'} ${detail}`.trim())
      }
      setMsg({ kind: 'ok', text: `Created ${form.email}. Map a bot below to activate their account.` })
      setForm({ email: '', firstName: '', lastName: '', phone: '', state: '', password: '' })
      mutate(KEY)
    } catch (err) {
      setMsg({ kind: 'err', text: err instanceof Error ? err.message : 'Something went wrong.' })
    } finally {
      setCreating(false)
    }
  }

  async function changeMap(customerId: string, bot: string, action: 'map' | 'unmap') {
    await fetch(KEY, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, customerId, bot }),
    })
    mutate(KEY)
  }

  const unauthorized = data && data.ok === false

  return (
    <div className="min-h-screen bg-forge-bg text-white">
      <div className="mx-auto max-w-[1000px] px-4 py-8">
        <h1 className="text-2xl font-bold">Customer Profiles</h1>
        <p className="mt-1 text-sm text-gray-400">
          Operator console — create a customer profile, then map them to the bot(s) they own. No mapping = empty
          dashboard.
        </p>

        {unauthorized ? (
          <div className="mt-6 rounded-xl border border-forge-border bg-forge-card/80 p-6 text-sm text-gray-300">
            {data?.error ?? 'Operator session required.'} Sign in with your operator link, then reload this page.
          </div>
        ) : (
          <>
            {/* Create profile */}
            <section className="mt-6 rounded-xl border border-forge-border bg-forge-card/80 p-5">
              <h2 className="text-sm font-bold uppercase tracking-wide text-amber-500">Add a profile</h2>
              <form onSubmit={createProfile} className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <input className={input} placeholder="First name" value={form.firstName} onChange={set('firstName')} />
                <input className={input} placeholder="Last name" value={form.lastName} onChange={set('lastName')} />
                <input className={input} placeholder="Email" type="email" value={form.email} onChange={set('email')} />
                <input className={input} placeholder="Password (min 8 chars)" type="text" value={form.password} onChange={set('password')} />
                <input className={input} placeholder="Phone (optional)" value={form.phone} onChange={set('phone')} />
                <input className={input} placeholder="State (optional)" value={form.state} onChange={set('state')} />
                <div className="sm:col-span-2 flex items-center gap-3">
                  <button className={btn} disabled={creating} type="submit">
                    {creating ? 'Creating…' : 'Create profile'}
                  </button>
                  {msg && (
                    <span className={`text-sm ${msg.kind === 'ok' ? 'text-emerald-400' : 'text-red-400'}`}>{msg.text}</span>
                  )}
                </div>
              </form>
            </section>

            {/* Existing profiles */}
            <section className="mt-6 rounded-xl border border-forge-border bg-forge-card/80">
              <div className="border-b border-forge-border px-5 py-3 text-sm font-bold uppercase tracking-wide text-amber-500">
                Profiles {data ? `(${data.customers.length})` : ''}
              </div>
              {isLoading && <div className="p-5 text-sm text-gray-400">Loading…</div>}
              {error && <div className="p-5 text-sm text-red-400">Failed to load profiles.</div>}
              {data?.ok && data.customers.length === 0 && (
                <div className="p-5 text-sm text-gray-400">No profiles yet. Add one above.</div>
              )}
              {data?.ok && data.customers.length > 0 && (
                <div className="divide-y divide-forge-border">
                  {data.customers.map((c) => (
                    <div key={c.id} className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="font-semibold">{c.name || '—'}</div>
                        <div className="text-sm text-gray-400">{c.email}</div>
                        <div className="mt-0.5 text-xs text-gray-500">
                          {c.status}
                          {!c.emailVerified && ' · email not verified'}
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {c.bots.length === 0 && <span className="text-xs text-gray-500">no bot mapped</span>}
                        {c.bots.map((b) => (
                          <button
                            key={b}
                            onClick={() => changeMap(c.id, b, 'unmap')}
                            title="Click to remove"
                            className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-300 hover:border-red-500/60 hover:bg-red-500/15 hover:text-red-300"
                          >
                            {b} ✕
                          </button>
                        ))}
                        <BotAdder
                          options={(data.bots ?? []).filter((o) => !c.bots.includes(o.id))}
                          onAdd={(bot) => changeMap(c.id, bot, 'map')}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  )
}

function BotAdder({ options, onAdd }: { options: BotOpt[]; onAdd: (bot: string) => void }) {
  const [val, setVal] = useState('')
  if (options.length === 0) return null
  return (
    <select
      value={val}
      onChange={(e) => {
        const bot = e.target.value
        if (bot) {
          onAdd(bot)
          setVal('')
        }
      }}
      className="rounded-md border border-forge-border bg-forge-bg px-2 py-1 text-xs text-gray-300 focus:border-amber-500 focus:outline-none"
    >
      <option value="">+ map bot…</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.id}
        </option>
      ))}
    </select>
  )
}
