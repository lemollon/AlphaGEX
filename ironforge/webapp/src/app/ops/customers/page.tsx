'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR, { mutate } from 'swr'
import { fetcher } from '@/lib/fetcher'

/**
 * Operator-only customer admin. Gated by the operator session server-side
 * (/api/ops/customers).
 *
 * A profile needs TWO separate things, and the page shows them as two separate
 * rows of chips because they fail in different ways:
 *
 *   Mapped   — which bot's ledger they see. Missing → the Live empty state.
 *   Member   — whether the apps unlock at all. Missing → a signed-in customer
 *              staring at a locked Forge, which looks like a broken build.
 *
 * Memberships bought through Stripe are shown but not editable here; the server
 * refuses to touch them, since cancelling one would end access while the card
 * keeps being charged.
 */

const KEY = '/api/ops/customers'

interface BotOpt { id: string; label: string }
interface Membership {
  bot: string
  status: string
  /** No Stripe subscription behind it — comped by an operator, editable here. */
  comped: boolean
}
interface Customer {
  id: string
  email: string
  name: string
  status: string
  emailVerified: boolean
  createdAt: string
  bots: string[]
  memberships: Membership[]
  promoCode: string | null
}
interface ListResp {
  ok: boolean
  error?: string
  bots: BotOpt[]
  grantable: string[]
  customers: Customer[]
}

/** Statuses that actually unlock the app — mirrors LIVE_STATUSES server-side. */
const LIVE_STATUSES = new Set(['trialing', 'active', 'past_due'])

const input =
  'w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-amber-500 focus:outline-none'
const btn =
  'rounded-md bg-amber-500 px-4 py-2 text-sm font-semibold text-black transition hover:bg-amber-400 disabled:opacity-50'

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
      setMsg({
        kind: 'ok',
        text: `Created ${form.email}. Now grant a membership AND map a bot — they are separate.`,
      })
      setForm({ email: '', firstName: '', lastName: '', phone: '', state: '', password: '' })
      mutate(KEY)
    } catch (err) {
      setMsg({ kind: 'err', text: err instanceof Error ? err.message : 'Something went wrong.' })
    } finally {
      setCreating(false)
    }
  }

  async function post(action: string, customerId: string, bot: string) {
    const res = await fetch(KEY, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, customerId, bot }),
    })
    // Surface the refusal instead of swallowing it — a silently ignored click on a
    // Stripe-owned membership would read as "the button is broken".
    const j = await res.json().catch(() => ({}))
    if (!res.ok || !j.ok) setMsg({ kind: 'err', text: j.error ?? 'That change did not apply.' })
    mutate(KEY)
  }

  const unauthorized = data && data.ok === false

  return (
    <div className="min-h-screen bg-forge-bg text-white">
      <div className="mx-auto max-w-[1000px] px-4 py-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">Customer Profiles</h1>
          <Link href="/ops/traffic" className="text-sm font-semibold text-amber-400 underline hover:text-amber-300">
            Traffic
          </Link>
        </div>
        <p className="mt-1 text-sm text-gray-400">
          Operator console — create a profile, grant the membership that unlocks the apps, and map the bot whose
          ledger they see. Those are two different switches; a customer needs both.
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
                        {c.promoCode && (
                          <div className="mt-1 inline-flex items-center gap-1 rounded border border-amber-600/40 bg-amber-950/30 px-1.5 py-0.5 text-[11px] font-semibold text-amber-400">
                            PROMO {c.promoCode} · honour 2 bots @ $50/mo
                          </div>
                        )}
                      </div>
                      <div className="flex flex-col gap-2 sm:items-end">
                        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                          <span className="text-[11px] uppercase tracking-wide text-gray-500">Member</span>
                          {live(c).length === 0 && <span className="text-xs text-red-400">apps locked</span>}
                          {c.memberships
                            .filter((m) => LIVE_STATUSES.has(m.status))
                            .map((m) => (
                              <button
                                key={m.bot}
                                onClick={() => m.comped && post('revoke', c.id, m.bot)}
                                disabled={!m.comped}
                                title={m.comped ? 'Comped — click to cancel' : 'Billed through Stripe — change it in Stripe'}
                                className={
                                  m.comped
                                    ? 'rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-1 text-xs font-medium text-emerald-300 hover:border-red-500/60 hover:bg-red-500/15 hover:text-red-300'
                                    : 'cursor-default rounded-full border border-sky-500/40 bg-sky-500/10 px-2.5 py-1 text-xs font-medium text-sky-300'
                                }
                              >
                                {m.bot}
                                {m.comped ? ' ✕' : ' · stripe'}
                              </button>
                            ))}
                          <BotAdder
                            label="+ grant…"
                            options={(data.grantable ?? [])
                              .filter((id) => !live(c).includes(id))
                              .map((id) => ({ id, label: id }))}
                            onAdd={(bot) => post('grant', c.id, bot)}
                          />
                        </div>
                        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
                          <span className="text-[11px] uppercase tracking-wide text-gray-500">Mapped</span>
                          {c.bots.length === 0 && <span className="text-xs text-gray-500">no bot mapped</span>}
                          {c.bots.map((b) => (
                            <button
                              key={b}
                              onClick={() => post('unmap', c.id, b)}
                              title="Click to remove"
                              className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-300 hover:border-red-500/60 hover:bg-red-500/15 hover:text-red-300"
                            >
                              {b} ✕
                            </button>
                          ))}
                          <BotAdder
                            label="+ map bot…"
                            options={(data.bots ?? []).filter((o) => !c.bots.includes(o.id))}
                            onAdd={(bot) => post('map', c.id, bot)}
                          />
                        </div>
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

/** The memberships currently unlocking the app for this customer. */
function live(c: Customer): string[] {
  return c.memberships.filter((m) => LIVE_STATUSES.has(m.status)).map((m) => m.bot)
}

function BotAdder({
  options,
  onAdd,
  label,
}: {
  options: BotOpt[]
  onAdd: (bot: string) => void
  label: string
}) {
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
      <option value="">{label}</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.id}
        </option>
      ))}
    </select>
  )
}
