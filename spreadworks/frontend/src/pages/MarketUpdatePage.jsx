// Market Update — the morning and intraday SpreadWorks reports, plus the full
// archive, in one tab. Leron, 2026-10-12: "it should be added as a tab in
// spreadworks under market update, i want the morning and intraday reports to
// go there along with the archived reports." The reports themselves are
// generated server-side (backend/full_options_report.py,
// backend/morning_options_report.py) as standalone dark-themed HTML pages
// with charts embedded as base64 PNGs — nothing to re-render here, so the
// report body is an <iframe> onto GET /api/spreadworks/reports/{id}/view
// (no X-Frame-Options/CSP set server-side, confirmed before building this).
// This page is just the browsing/selection shell: a kind filter, a sortable
// history list (GET /api/spreadworks/reports/history), and the viewer.
//
// Leron, 2026-10-16: "the report looks super ugly ... complete overhaul and
// redesign." Keeps every piece of behavior (fetch, filter, select, iframe) —
// only the markup/styling changed, from a bespoke inline-style sheet to the
// site-wide AURORA design system (sw-glass/sw-card/sw-badge/sw-toggle-group,
// index.css) that every other SpreadWorks page already uses, so this page no
// longer looks like a different, unfinished app bolted onto the rest.
import { useEffect, useMemo, useState } from 'react';
import { Newspaper, RefreshCw, ExternalLink, FileDown, Archive } from 'lucide-react';
import { API_URL } from '../lib/api';

const KIND_LABEL = { morning: 'Morning', market_open: 'Market Open', intraday: 'Intraday' };
// Matches the exact dim/border rgba pattern index.css already uses for every other
// semantic badge (e.g. .sw-btn-danger's rose ring) -- color-mix() would work too, but
// this keeps the kind badges on the same literal-rgba convention as the rest of AURORA
// instead of introducing a different technique for one component.
const KIND_STYLE = {
  morning: { color: 'var(--color-sw-yellow)', background: 'var(--color-sw-yellow-dim)', border: 'rgba(252,211,77,0.35)' },
  market_open: { color: 'var(--color-info)', background: 'var(--color-info-soft)', border: 'rgba(125,211,252,0.35)' },
  intraday: { color: 'var(--color-sw-green)', background: 'var(--color-sw-green-dim)', border: 'rgba(52,211,153,0.35)' },
};

function timeAgo(iso) {
  if (!iso) return '';
  const diffMs = Date.now() - new Date(iso).getTime();
  const h = diffMs / 3600000;
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m ago`;
  if (h < 48) return `${h.toFixed(1)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function thesisText(thesis) {
  if (!thesis) return null;
  if (thesis.status === 'unavailable') return null;
  const v = thesis.value;
  return typeof v === 'string' ? v : null;
}

function KindBadge({ kind }) {
  const s = KIND_STYLE[kind] || { color: 'var(--color-text-tertiary)', background: 'transparent', border: 'var(--color-border-default)' };
  return (
    <span className="sw-badge" style={{ color: s.color, background: s.background, boxShadow: `inset 0 0 0 1px ${s.border}` }}>
      {KIND_LABEL[kind] || kind}
    </span>
  );
}

export default function MarketUpdatePage() {
  const [reports, setReports] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [kindFilter, setKindFilter] = useState('all');
  const [selectedId, setSelectedId] = useState(null);

  const [reloadKey, setReloadKey] = useState(0);
  const reload = () => setReloadKey((k) => k + 1);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    const qs = new URLSearchParams({ limit: '60' });
    if (kindFilter !== 'all') qs.set('kind', kindFilter);
    fetch(`${API_URL}/api/spreadworks/reports/history?${qs.toString()}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((j) => {
        if (!alive) return;
        const list = j.reports || [];
        setReports(list);
        setTotal(j.total ?? list.length);
        setSelectedId((prev) => (prev && list.some((r) => r.report_id === prev) ? prev : list[0]?.report_id || null));
        setLoading(false);
      })
      .catch((e) => {
        if (alive) { setErr(e.message); setLoading(false); }
      });
    return () => { alive = false; };
  }, [kindFilter, reloadKey]);

  const selected = useMemo(
    () => reports.find((r) => r.report_id === selectedId) || null,
    [reports, selectedId],
  );

  const kinds = ['all', 'morning', 'market_open', 'intraday'];

  return (
    <div className="w-full max-w-[1400px] mx-auto flex flex-col gap-4" style={{ padding: '24px 16px 96px' }}>
      <div className="flex justify-between items-start gap-3 flex-wrap">
        <div>
          <h1 className="flex items-center gap-2.5 font-semibold text-text-primary" style={{ fontSize: 22 }}>
            <Newspaper size={20} style={{ color: 'var(--color-accent)' }} /> Market Update
          </h1>
          <p className="text-text-tertiary" style={{ fontSize: 13, marginTop: 4 }}>
            Morning and intraday SpreadWorks reports, plus the full archive — {total} reports on file.
          </p>
        </div>
        <button type="button" className="sw-btn-ghost flex items-center gap-1.5" onClick={reload} title="Refresh list">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div className="sw-toggle-group" style={{ maxWidth: 480 }}>
        {kinds.map((k) => (
          <button
            key={k}
            type="button"
            className={`sw-toggle-btn${kindFilter === k ? ' active' : ''}`}
            onClick={() => setKindFilter(k)}
          >
            {k === 'all' ? 'All reports' : KIND_LABEL[k]}
          </button>
        ))}
      </div>

      <div className="flex gap-4 items-start flex-wrap">
        <div className="flex-none flex flex-col gap-2.5" style={{ width: 340 }}>
          <div className="sw-card" style={{ padding: 14 }}>
            {err && <div className="text-sw-red" style={{ fontSize: 13, padding: 14 }}>{err}</div>}
            {!err && loading && <div className="text-text-tertiary text-center" style={{ fontSize: 13, padding: '24px 8px' }}>Loading…</div>}
            {!err && !loading && reports.length === 0 && (
              <div className="text-text-tertiary text-center" style={{ fontSize: 13, padding: '24px 8px' }}>
                <Archive size={20} style={{ color: 'var(--color-text-tertiary)', marginBottom: 6 }} />
                <div>No reports in this filter yet.</div>
              </div>
            )}
            {!err && !loading && reports.length > 0 && (
              <div className="flex flex-col gap-1.5 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 260px)' }}>
                {reports.map((r) => {
                  const active = r.report_id === selectedId;
                  const t = thesisText(r.thesis);
                  return (
                    <button
                      type="button"
                      key={r.report_id}
                      onClick={() => setSelectedId(r.report_id)}
                      className="flex flex-col gap-1 text-left rounded-lg transition-colors"
                      style={{
                        padding: '10px 12px',
                        border: active ? '1px solid var(--color-border-accent)' : '1px solid transparent',
                        background: active ? 'var(--color-accent-dim)' : 'var(--color-bg-deep)',
                      }}
                    >
                      <div className="flex justify-between items-center gap-2">
                        <KindBadge kind={r.kind} />
                        <span className="text-text-tertiary" style={{ fontSize: 11 }}>{r.trading_date} · {r.time_ct} CT</span>
                      </div>
                      {t && <div className="text-text-body" style={{ fontSize: 12, lineHeight: 1.35 }}>{t}</div>}
                      <div className="text-text-tertiary" style={{ fontSize: 11 }}>
                        {timeAgo(r.generated_at)}{r.chart_count != null ? ` · ${r.chart_count} charts` : ''}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0" style={{ flexBasis: 600 }}>
          {selected ? (
            <>
              <div className="flex justify-between items-center gap-2.5 flex-wrap" style={{ marginBottom: 10 }}>
                <KindBadge kind={selected.kind} />
                <span className="text-text-tertiary" style={{ fontSize: 12 }}>
                  {selected.trading_date} · {selected.time_ct} CT · {timeAgo(selected.generated_at)}
                </span>
                <div className="flex items-center gap-2.5">
                  <a
                    className="flex items-center gap-1 no-underline"
                    style={{ fontSize: 12, color: 'var(--color-accent)' }}
                    href={selected.report_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <ExternalLink size={13} /> Open full page
                  </a>
                  {selected.report_pdf_url && (
                    <a
                      className="flex items-center gap-1 no-underline"
                      style={{ fontSize: 12, color: 'var(--color-accent)' }}
                      href={selected.report_pdf_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <FileDown size={13} /> Download PDF
                    </a>
                  )}
                  {selected.pdf_url && (
                    <a
                      className="flex items-center gap-1 no-underline"
                      style={{ fontSize: 12, color: 'var(--color-accent)' }}
                      href={selected.pdf_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <FileDown size={13} /> Charts PDF
                    </a>
                  )}
                </div>
              </div>
              <div className="sw-glass rounded-xl overflow-hidden">
                <iframe
                  key={selected.report_id}
                  src={selected.report_url}
                  className="w-full block border-0"
                  style={{ height: 'calc(100vh - 300px)', minHeight: 640 }}
                  title={`${KIND_LABEL[selected.kind] || selected.kind} report ${selected.trading_date}`}
                />
              </div>
            </>
          ) : (
            <div className="sw-card text-text-tertiary text-center" style={{ padding: '24px 8px', fontSize: 13 }}>
              Select a report from the archive to view it.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
