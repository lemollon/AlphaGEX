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
import { useEffect, useMemo, useState } from 'react';
import { Newspaper, RefreshCw, ExternalLink, FileDown, Archive } from 'lucide-react';
import { API_URL } from '../lib/api';

const DIM = '#8b93a7';
const ACCENT = '#22d3ee';

const KIND_LABEL = { morning: 'Morning', market_open: 'Market Open', intraday: 'Intraday' };
const KIND_COLOR = { morning: '#fbbf24', market_open: '#60a5fa', intraday: '#34d399' };

const S = {
  wrap: { width: '100%', maxWidth: 1400, margin: '0 auto', padding: '24px 16px 96px', display: 'flex', flexDirection: 'column', gap: 16 },
  h1: { fontSize: 22, fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: 10 },
  sub: { color: DIM, fontSize: 13, margin: '4px 0 0' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 },
  body: { display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' },
  sidebar: { width: 340, flex: '0 0 340px', display: 'flex', flexDirection: 'column', gap: 10 },
  main: { flex: '1 1 600px', minWidth: 0 },
  card: { background: '#141824', border: '1px solid #232a3d', borderRadius: 12, padding: 14 },
  tabRow: { display: 'flex', gap: 6, flexWrap: 'wrap' },
  tab: (active) => ({
    fontSize: 12, fontWeight: 600, padding: '6px 12px', borderRadius: 999, cursor: 'pointer',
    border: active ? `1px solid ${ACCENT}` : '1px solid #232a3d',
    background: active ? 'rgba(34,211,238,0.12)' : 'transparent',
    color: active ? '#e6f9fd' : DIM,
  }),
  refreshBtn: {
    display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 600,
    color: DIM, background: 'transparent', border: '1px solid #232a3d', borderRadius: 8,
    padding: '6px 10px', cursor: 'pointer',
  },
  list: { display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 'calc(100vh - 260px)', overflowY: 'auto' },
  row: (active) => ({
    display: 'flex', flexDirection: 'column', gap: 4, textAlign: 'left',
    padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
    border: active ? `1px solid ${ACCENT}` : '1px solid transparent',
    background: active ? 'rgba(34,211,238,0.08)' : '#0e1220',
  }),
  rowTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  badge: (kind) => ({
    fontSize: 10, fontWeight: 700, borderRadius: 4, padding: '2px 6px',
    color: KIND_COLOR[kind] || DIM, background: `${KIND_COLOR[kind] || DIM}1a`,
    textTransform: 'uppercase', letterSpacing: 0.4, whiteSpace: 'nowrap',
  }),
  rowMeta: { fontSize: 11, color: DIM },
  rowThesis: { fontSize: 12, color: '#cbd5e1', lineHeight: 1.35 },
  empty: { fontSize: 13, color: DIM, padding: '24px 8px', textAlign: 'center' },
  err: { fontSize: 13, color: '#f87171', padding: '14px' },
  viewerHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 },
  viewerLinks: { display: 'flex', gap: 10, alignItems: 'center' },
  link: { display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: ACCENT, textDecoration: 'none' },
  iframeWrap: { border: '1px solid #232a3d', borderRadius: 12, overflow: 'hidden', background: '#0b0e13' },
  iframe: { width: '100%', height: 'calc(100vh - 300px)', minHeight: 640, border: 'none', display: 'block' },
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
    <div style={S.wrap}>
      <div style={S.header}>
        <div>
          <h1 style={S.h1}><Newspaper size={20} color={ACCENT} /> Market Update</h1>
          <p style={S.sub}>Morning and intraday SpreadWorks reports, plus the full archive — {total} reports on file.</p>
        </div>
        <button style={S.refreshBtn} onClick={reload} title="Refresh list">
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div style={S.tabRow}>
        {kinds.map((k) => (
          <div key={k} style={S.tab(kindFilter === k)} onClick={() => setKindFilter(k)}>
            {k === 'all' ? 'All reports' : KIND_LABEL[k]}
          </div>
        ))}
      </div>

      <div style={S.body}>
        <div style={S.sidebar}>
          <div style={S.card}>
            {err && <div style={S.err}>{err}</div>}
            {!err && loading && <div style={S.empty}>Loading…</div>}
            {!err && !loading && reports.length === 0 && (
              <div style={S.empty}>
                <Archive size={20} color={DIM} style={{ marginBottom: 6 }} />
                <div>No reports in this filter yet.</div>
              </div>
            )}
            {!err && !loading && reports.length > 0 && (
              <div style={S.list}>
                {reports.map((r) => {
                  const active = r.report_id === selectedId;
                  const t = thesisText(r.thesis);
                  return (
                    <div key={r.report_id} style={S.row(active)} onClick={() => setSelectedId(r.report_id)}>
                      <div style={S.rowTop}>
                        <span style={S.badge(r.kind)}>{KIND_LABEL[r.kind] || r.kind}</span>
                        <span style={S.rowMeta}>{r.trading_date} · {r.time_ct} CT</span>
                      </div>
                      {t && <div style={S.rowThesis}>{t}</div>}
                      <div style={S.rowMeta}>{timeAgo(r.generated_at)}{r.chart_count != null ? ` · ${r.chart_count} charts` : ''}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div style={S.main}>
          {selected ? (
            <>
              <div style={S.viewerHeader}>
                <span style={S.badge(selected.kind)}>{KIND_LABEL[selected.kind] || selected.kind}</span>
                <span style={{ ...S.rowMeta, fontSize: 12 }}>{selected.trading_date} · {selected.time_ct} CT · {timeAgo(selected.generated_at)}</span>
                <div style={S.viewerLinks}>
                  <a style={S.link} href={selected.report_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={13} /> Open full page
                  </a>
                  {selected.pdf_url && (
                    <a style={S.link} href={selected.pdf_url} target="_blank" rel="noreferrer">
                      <FileDown size={13} /> Charts PDF
                    </a>
                  )}
                </div>
              </div>
              <div style={S.iframeWrap}>
                <iframe
                  key={selected.report_id}
                  src={selected.report_url}
                  style={S.iframe}
                  title={`${KIND_LABEL[selected.kind] || selected.kind} report ${selected.trading_date}`}
                />
              </div>
            </>
          ) : (
            <div style={{ ...S.card, ...S.empty }}>Select a report from the archive to view it.</div>
          )}
        </div>
      </div>
    </div>
  );
}
