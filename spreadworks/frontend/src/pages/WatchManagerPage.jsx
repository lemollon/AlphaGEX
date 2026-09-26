import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BellRing,
  CheckCircle2,
  CircleAlert,
  Clock3,
  History,
  KeyRound,
  Loader2,
  LockKeyhole,
  LogOut,
  RefreshCw,
  Send,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import { API_URL } from '../lib/api';

const SESSION_STORAGE_KEY = 'spreadworks_watch_manager_session';

const stateTone = {
  WAIT: 'border-white/10 bg-white/[0.04] text-slate-300',
  NEAR_TRIGGER: 'border-amber-300/25 bg-amber-300/10 text-amber-200',
  ENTRY_READY: 'border-emerald-300/30 bg-emerald-300/10 text-emerald-200',
  ACTIVE: 'border-cyan-300/30 bg-cyan-300/10 text-cyan-200',
  INVALIDATED: 'border-rose-300/30 bg-rose-300/10 text-rose-200',
  EXPIRED: 'border-white/10 bg-white/[0.03] text-slate-500',
  DATA_UNAVAILABLE: 'border-rose-300/25 bg-rose-300/10 text-rose-200',
  LIQUIDITY_BLOCKED: 'border-amber-300/25 bg-amber-300/10 text-amber-200',
};

function readStoredSession() {
  try {
    return localStorage.getItem(SESSION_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

function storeSession(value) {
  try {
    if (value) localStorage.setItem(SESSION_STORAGE_KEY, value);
    else localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // Private browsing can disable storage. The in-memory session still works.
  }
}

function apiErrorMessage(payload, fallback) {
  if (typeof payload?.detail === 'string') return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail.map((item) => item?.msg || String(item)).join(' ');
  }
  return fallback;
}

function titleCase(value) {
  return String(value || '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatEntry(entry) {
  if (!entry) return 'Entry rule unavailable';
  const bars = `${entry.confirmation_bars || 2} completed 1-minute bar${(entry.confirmation_bars || 2) === 1 ? '' : 's'}`;
  switch (entry.type) {
    case 'breakout_hold':
      return `Hold above ${entry.breakout_level} for ${bars}`;
    case 'breakout_retest':
      return `Break, retest, and hold ${entry.breakout_level} for ${bars}`;
    case 'support_hold':
      return `Hold support ${entry.support_low}–${entry.support_high} for ${bars}`;
    case 'failed_reclaim':
      return `Fail to reclaim ${entry.reclaim_level} for ${bars}`;
    case 'vwap_reclaim':
      return `Reclaim VWAP for ${bars}`;
    case 'opening_range_breakout':
      return `Break above ${entry.range_high} for ${bars}`;
    case 'opening_range_rejection':
      return `Reject ${entry.range_low}–${entry.range_high} and close below for ${bars}`;
    case 'opening_range_hold':
      return `Hold inside ${entry.range_low}–${entry.range_high} for ${bars}`;
    default:
      return titleCase(entry.type);
  }
}

function formatInvalidation(rule) {
  if (!rule) return 'Invalidation unavailable';
  if (rule.type === 'close_below') return `Completed close below ${rule.level}`;
  if (rule.type === 'close_above') return `Completed close above ${rule.level}`;
  if (rule.type === 'none') return 'No invalidation stated';
  return titleCase(rule.type);
}

function formatTimestamp(value) {
  if (!value) return 'Not yet';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }) + ' CT';
}

function Surface({ children, className = '' }) {
  return (
    <section className={`rounded-2xl border border-sky-200/[0.10] bg-[#07101c]/60 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] backdrop-blur-xl ${className}`}>
      {children}
    </section>
  );
}

function Unlock({ onUnlock, busy, error }) {
  const [accessKey, setAccessKey] = useState('');

  const submit = (event) => {
    event.preventDefault();
    if (accessKey.trim()) onUnlock(accessKey);
  };

  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto px-5 py-12">
      <Surface className="w-full max-w-md p-7">
        <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200">
          <LockKeyhole size={22} />
        </div>
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-cyan-300">Private operator page</p>
        <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-white">Unlock Watch Manager</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          Enter your Watch Manager access key once. This device stays signed in for 30 days.
        </p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">Access key</span>
            <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-[#050c15]/80 px-4 focus-within:border-cyan-300/50">
              <KeyRound size={16} className="shrink-0 text-slate-500" />
              <input
                type="password"
                value={accessKey}
                onChange={(event) => setAccessKey(event.target.value)}
                autoComplete="current-password"
                className="min-w-0 flex-1 bg-transparent py-3.5 text-sm text-white outline-none placeholder:text-slate-600"
                placeholder="Watch Manager key"
              />
            </div>
          </label>
          {error && (
            <div className="flex gap-2 rounded-xl border border-rose-300/20 bg-rose-300/10 px-3.5 py-3 text-sm text-rose-200">
              <CircleAlert size={17} className="mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <button
            type="submit"
            disabled={busy || !accessKey.trim()}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-400 px-4 py-3 text-sm font-extrabold text-slate-950 shadow-[0_0_28px_rgba(34,211,238,0.18)] disabled:opacity-40"
          >
            {busy ? <Loader2 size={17} className="animate-spin" /> : <ShieldCheck size={17} />}
            Unlock
          </button>
        </form>
      </Surface>
    </div>
  );
}

function Stat({ label, value, tone = 'text-white' }) {
  return (
    <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] px-4 py-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-extrabold ${tone}`}>{value}</div>
    </div>
  );
}

function WatchCard({ watch, onOutcome, outcomeBusy }) {
  const delivered = watch.alerts?.some((alert) => alert.posted);
  const entryAlert = watch.alerts?.find((alert) => alert.state === 'ENTRY_READY');
  const isWinner = watch.outcome === 'WINNER';
  const isLoser = watch.outcome === 'LOSER';

  return (
    <article className="rounded-2xl border border-sky-200/[0.09] bg-white/[0.025] p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg font-black text-white">{watch.symbol}</span>
            <span className="text-sm font-semibold text-slate-300">{titleCase(watch.strategy)}</span>
            <span className={`rounded-full border px-2.5 py-1 text-[10px] font-extrabold uppercase tracking-wider ${stateTone[watch.state] || stateTone.WAIT}`}>
              {titleCase(watch.state)}
            </span>
            {watch.origin === 'paste_to_watch' && (
              <span className="rounded-full border border-violet-300/20 bg-violet-300/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-violet-200">
                Pasted
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-slate-500">{watch.trading_date} · {titleCase(watch.thesis)}</div>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            disabled={outcomeBusy}
            onClick={() => onOutcome(watch.setup_id, 'WINNER')}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold ${isWinner ? 'border-emerald-300/40 bg-emerald-300/20 text-emerald-100' : 'border-white/10 bg-white/[0.03] text-slate-400 hover:border-emerald-300/30 hover:text-emerald-200'}`}
          >
            <ThumbsUp size={14} /> Winner
          </button>
          <button
            type="button"
            disabled={outcomeBusy}
            onClick={() => onOutcome(watch.setup_id, 'LOSER')}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-bold ${isLoser ? 'border-rose-300/40 bg-rose-300/20 text-rose-100' : 'border-white/10 bg-white/[0.03] text-slate-400 hover:border-rose-300/30 hover:text-rose-200'}`}
          >
            <ThumbsDown size={14} /> Loser
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-white/[0.06] bg-[#050c15]/55 p-3.5">
          <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-cyan-300">Entry</div>
          <div className="mt-1.5 text-sm font-semibold leading-5 text-slate-200">{formatEntry(watch.entry)}</div>
          {watch.confirmation_defaulted && (
            <div className="mt-1.5 text-[11px] text-slate-500">Uses the standard 2-bar confirmation because the paste did not specify one.</div>
          )}
        </div>
        <div className="rounded-xl border border-white/[0.06] bg-[#050c15]/55 p-3.5">
          <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-rose-300">Invalidation</div>
          <div className="mt-1.5 text-sm font-semibold leading-5 text-slate-200">{formatInvalidation(watch.invalidation)}</div>
        </div>
      </div>

      <div className="mt-4 grid gap-2 text-xs text-slate-400 sm:grid-cols-3">
        <div className="flex items-center gap-2">
          <BellRing size={14} className={delivered ? 'text-emerald-300' : 'text-slate-600'} />
          {delivered ? 'Discord transition delivered' : 'No Discord transition yet'}
        </div>
        <div className="flex items-center gap-2">
          <Clock3 size={14} className="text-slate-600" />
          Trigger: {entryAlert ? formatTimestamp(entryAlert.transition_at) : 'not hit'}
        </div>
        <div className="flex items-center gap-2">
          <History size={14} className="text-slate-600" />
          Added: {formatTimestamp(watch.created_at)}
        </div>
      </div>

      {watch.original_text && (
        <details className="mt-4 border-t border-white/[0.06] pt-3">
          <summary className="cursor-pointer text-xs font-semibold text-slate-500 hover:text-slate-300">Show original pasted idea</summary>
          <div className="mt-3 whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-black/20 p-3 text-xs leading-5 text-slate-400">
            {watch.original_text}
          </div>
        </details>
      )}
    </article>
  );
}

export default function WatchManagerPage() {
  const [sessionToken, setSessionToken] = useState(readStoredSession);
  const [authenticated, setAuthenticated] = useState(null);
  const [unlockBusy, setUnlockBusy] = useState(false);
  const [unlockError, setUnlockError] = useState('');
  const [pasteText, setPasteText] = useState('');
  const [submitBusy, setSubmitBusy] = useState(false);
  const [submitMessage, setSubmitMessage] = useState(null);
  const [history, setHistory] = useState({ watches: [], total: 0, counts: {} });
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyError, setHistoryError] = useState('');
  const [worker, setWorker] = useState(null);
  const [filter, setFilter] = useState('ALL');
  const [outcomeBusy, setOutcomeBusy] = useState('');

  const signOut = useCallback(() => {
    storeSession('');
    setSessionToken('');
    setAuthenticated(false);
    setHistory({ watches: [], total: 0, counts: {} });
  }, []);

  const authedFetch = useCallback(async (path, options = {}) => {
    const response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-Watch-Manager-Session': sessionToken,
        ...(options.headers || {}),
      },
    });
    let payload = {};
    try { payload = await response.json(); } catch { /* keep fallback */ }
    if (response.status === 401) {
      signOut();
      throw new Error('Your Watch Manager session expired. Unlock it again.');
    }
    if (!response.ok) {
      throw new Error(apiErrorMessage(payload, `Request failed (${response.status})`));
    }
    return payload;
  }, [sessionToken, signOut]);

  const loadHistory = useCallback(async ({ quiet = false } = {}) => {
    if (!sessionToken) return;
    if (!quiet) setHistoryBusy(true);
    try {
      const payload = await authedFetch('/api/spreadworks/watch-manager/watches?limit=200');
      setHistory(payload);
      setHistoryError('');
    } catch (error) {
      setHistoryError(error.message);
    } finally {
      if (!quiet) setHistoryBusy(false);
    }
  }, [authedFetch, sessionToken]);

  const loadWorker = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/spreadworks/intraday-watch/status`);
      if (response.ok) setWorker(await response.json());
    } catch {
      // The page history remains useful if public heartbeat retrieval fails.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function validate() {
      if (!sessionToken) {
        setAuthenticated(false);
        return;
      }
      try {
        const response = await fetch(`${API_URL}/api/spreadworks/watch-manager/session`, {
          headers: { 'X-Watch-Manager-Session': sessionToken },
        });
        const payload = await response.json();
        if (cancelled) return;
        if (payload.authenticated) setAuthenticated(true);
        else signOut();
      } catch {
        if (!cancelled) setAuthenticated(false);
      }
    }
    validate();
    return () => { cancelled = true; };
  }, [sessionToken, signOut]);

  useEffect(() => {
    if (!authenticated) return undefined;
    loadHistory();
    loadWorker();
    const id = setInterval(() => {
      loadHistory({ quiet: true });
      loadWorker();
    }, 30_000);
    return () => clearInterval(id);
  }, [authenticated, loadHistory, loadWorker]);

  const unlock = async (accessKey) => {
    setUnlockBusy(true);
    setUnlockError('');
    try {
      const response = await fetch(`${API_URL}/api/spreadworks/watch-manager/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_key: accessKey }),
      });
      let payload = {};
      try { payload = await response.json(); } catch { /* keep fallback */ }
      if (!response.ok) throw new Error(apiErrorMessage(payload, 'Unable to unlock Watch Manager.'));
      storeSession(payload.session_token);
      setSessionToken(payload.session_token);
      setAuthenticated(true);
    } catch (error) {
      setUnlockError(error.message);
    } finally {
      setUnlockBusy(false);
    }
  };

  const addWatch = async (event) => {
    event.preventDefault();
    if (!pasteText.trim()) return;
    setSubmitBusy(true);
    setSubmitMessage(null);
    try {
      const payload = await authedFetch('/api/spreadworks/watch-manager/watches', {
        method: 'POST',
        body: JSON.stringify({ text: pasteText }),
      });
      setSubmitMessage({ type: 'success', text: payload.message });
      if (payload.added) setPasteText('');
      await loadHistory({ quiet: true });
      await loadWorker();
    } catch (error) {
      setSubmitMessage({ type: 'error', text: error.message });
    } finally {
      setSubmitBusy(false);
    }
  };

  const setOutcome = async (setupId, outcome) => {
    setOutcomeBusy(setupId);
    try {
      await authedFetch(`/api/spreadworks/watch-manager/watches/${encodeURIComponent(setupId)}/outcome`, {
        method: 'PATCH',
        body: JSON.stringify({ outcome }),
      });
      setHistory((current) => ({
        ...current,
        watches: current.watches.map((watch) => (
          watch.setup_id === setupId ? { ...watch, outcome } : watch
        )),
      }));
    } catch (error) {
      setHistoryError(error.message);
    } finally {
      setOutcomeBusy('');
    }
  };

  const filtered = useMemo(() => {
    if (filter === 'ALL') return history.watches;
    if (filter === 'ACTIVE') return history.watches.filter((watch) => watch.active && !['EXPIRED', 'INVALIDATED'].includes(watch.state));
    return history.watches.filter((watch) => watch.outcome === filter);
  }, [filter, history.watches]);

  const activeCount = history.watches.filter((watch) => watch.active && !['EXPIRED', 'INVALIDATED'].includes(watch.state)).length;
  const entryReadyCount = history.watches.filter((watch) => watch.state === 'ENTRY_READY').length;

  if (authenticated === null) {
    return <div className="flex flex-1 items-center justify-center text-slate-500"><Loader2 className="animate-spin" /></div>;
  }
  if (!authenticated) {
    return <Unlock onUnlock={unlock} busy={unlockBusy} error={unlockError} />;
  }

  return (
    <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl pb-12">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.18em] text-cyan-300">
              <BellRing size={15} /> Render entry engine
            </div>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-white">Watch Manager</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Paste one complete trade idea. SpreadWorks extracts the rules, refuses missing price levels, and adds it to Render’s near-real-time Discord watch.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => { loadHistory(); loadWorker(); }}
              disabled={historyBusy}
              className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-bold text-slate-300"
            >
              <RefreshCw size={14} className={historyBusy ? 'animate-spin' : ''} /> Refresh
            </button>
            <button
              type="button"
              onClick={signOut}
              className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs font-bold text-slate-400"
            >
              <LogOut size={14} /> Lock
            </button>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Render worker" value={worker?.worker_healthy ? 'Healthy' : 'Unavailable'} tone={worker?.worker_healthy ? 'text-emerald-300' : 'text-rose-300'} />
          <Stat label="Detection cadence" value={worker?.poll_interval_seconds ? `${worker.poll_interval_seconds}s` : '—'} />
          <Stat label="Active watches" value={activeCount} />
          <Stat label="Entry ready" value={entryReadyCount} tone={entryReadyCount ? 'text-emerald-300' : 'text-white'} />
        </div>

        <Surface className="mt-6 p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-cyan-300/20 bg-cyan-300/10 text-cyan-200">
              <Send size={17} />
            </div>
            <div>
              <h2 className="text-lg font-extrabold text-white">Paste to watch</h2>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Include the ticker, options strategy, numeric entry trigger, and numeric invalidation. Exact strikes can wait for fresh chain data.
              </p>
            </div>
          </div>
          <form onSubmit={addWatch} className="mt-5">
            <textarea
              value={pasteText}
              onChange={(event) => setPasteText(event.target.value)}
              rows={8}
              maxLength={12000}
              className="w-full resize-y rounded-xl border border-white/10 bg-[#050c15]/80 p-4 text-sm leading-6 text-slate-200 outline-none placeholder:text-slate-600 focus:border-cyan-300/50 focus:shadow-[0_0_0_2px_rgba(34,211,238,0.12)]"
              placeholder="Paste the full trade idea from ChatGPT here…"
            />
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-[11px] text-slate-600">Advisory only · no broker orders · today only</div>
              <button
                type="submit"
                disabled={submitBusy || !pasteText.trim()}
                className="flex items-center justify-center gap-2 rounded-xl bg-cyan-400 px-5 py-3 text-sm font-extrabold text-slate-950 shadow-[0_0_28px_rgba(34,211,238,0.18)] disabled:opacity-40"
              >
                {submitBusy ? <Loader2 size={17} className="animate-spin" /> : <BellRing size={17} />}
                {submitBusy ? 'Checking the rules…' : 'Add to Render Watch'}
              </button>
            </div>
          </form>
          {submitMessage && (
            <div className={`mt-4 flex gap-2 rounded-xl border px-4 py-3 text-sm ${submitMessage.type === 'success' ? 'border-emerald-300/20 bg-emerald-300/10 text-emerald-200' : 'border-rose-300/20 bg-rose-300/10 text-rose-200'}`}>
              {submitMessage.type === 'success' ? <CheckCircle2 size={17} className="mt-0.5 shrink-0" /> : <CircleAlert size={17} className="mt-0.5 shrink-0" />}
              <span>{submitMessage.text}</span>
            </div>
          )}
        </Surface>

        <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-extrabold uppercase tracking-[0.16em] text-slate-500">
              <History size={14} /> Historical watches
            </div>
            <h2 className="mt-1 text-xl font-black text-white">Every setup and outcome</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {['ALL', 'ACTIVE', 'WINNER', 'LOSER'].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`rounded-lg border px-3 py-2 text-[11px] font-extrabold uppercase tracking-wider ${filter === value ? 'border-cyan-300/30 bg-cyan-300/12 text-cyan-200' : 'border-white/[0.08] bg-white/[0.025] text-slate-500'}`}
              >
                {titleCase(value)}
              </button>
            ))}
          </div>
        </div>

        {historyError && (
          <div className="mt-4 flex gap-2 rounded-xl border border-rose-300/20 bg-rose-300/10 px-4 py-3 text-sm text-rose-200">
            <CircleAlert size={17} className="mt-0.5 shrink-0" /> {historyError}
          </div>
        )}

        <div className="mt-4 space-y-3">
          {historyBusy && !history.watches.length ? (
            <Surface className="flex items-center justify-center gap-2 p-10 text-sm text-slate-500">
              <Loader2 size={17} className="animate-spin" /> Loading watches…
            </Surface>
          ) : filtered.length ? (
            filtered.map((watch) => (
              <WatchCard
                key={watch.setup_id}
                watch={watch}
                onOutcome={setOutcome}
                outcomeBusy={outcomeBusy === watch.setup_id}
              />
            ))
          ) : (
            <Surface className="p-10 text-center">
              <History size={24} className="mx-auto text-slate-600" />
              <div className="mt-3 text-sm font-bold text-slate-300">No watches in this view</div>
              <div className="mt-1 text-xs text-slate-600">Paste an actionable idea above or choose another filter.</div>
            </Surface>
          )}
        </div>
      </div>
    </main>
  );
}
