import { useEffect, useState } from 'react';
import { Pencil } from 'lucide-react';
import { botApi } from '../../lib/botApi';
import { BOT_REGISTRY, STRATEGY_LABEL } from '../../lib/botRegistry';

const PT_GREEN = '#34d399';   // emerald-400
const SL_RED   = '#fb7185';   // rose-400

function fmtPct(v, digits = 0) {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return `${(Number(v) * 100).toFixed(digits)}%`;
}

function fmtMoney(v) {
  if (v == null || Number.isNaN(Number(v))) return '—';
  return `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function fmtSd(v) {
  if (v == null) return '—';
  return `${Number(v).toFixed(2)}σ`;
}

// Build the read-only section model from live config + bot meta.
function buildSections(bot, cfg) {
  const meta = BOT_REGISTRY[bot] || {};
  const isIBF = meta.strategy === 'iron_butterfly';

  const strategyRows = [
    { label: 'Strategy type', value: STRATEGY_LABEL[meta.strategy] || meta.strategy || '—' },
    { label: 'Underlying',    value: meta.ticker || '—' },
    {
      label: isIBF ? 'DTE Target' : 'Front DTE',
      value: cfg.front_dte != null ? String(cfg.front_dte) : '0 (same-day)',
    },
  ];
  if (!isIBF) {
    strategyRows.push({ label: 'Back DTE', value: cfg.back_dte != null ? String(cfg.back_dte) : '—' });
  }

  return [
    { section: 'Strategy', rows: strategyRows },
    { section: 'Sizing',   rows: [
      { label: 'Max Contracts',    value: String(cfg.max_contracts ?? '—') },
      { label: 'Buying Power %',   value: fmtPct(cfg.bp_pct, 0) },
      { label: 'Starting Capital', value: fmtMoney(cfg.starting_capital) },
    ]},
    { section: 'Filters',  rows: [
      { label: 'Std Deviation',  value: fmtSd(cfg.sd_mult) },
      { label: 'Delta Skew',     value: cfg.delta_skew != null ? String(cfg.delta_skew) : '0' },
      { label: 'Use GEX Walls',  value: cfg.use_gex_walls ? 'On' : 'Off' },
    ]},
    { section: 'Exits',    rows: [
      { label: 'Profit Take', value: fmtPct(cfg.pt_pct, 0),  accent: PT_GREEN },
      { label: 'Stop Loss',   value: fmtPct(cfg.sl_pct, 0),  accent: SL_RED },
      { label: 'EOD Close',   value: `${cfg.eod_close_ct || '—'} CT` },
      { label: 'Entry Window', value: `${cfg.entry_start_ct || '—'} – ${cfg.entry_end_ct || '—'} CT` },
    ]},
  ];
}

function ReadOnlySection({ section }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] font-bold text-text-tertiary mb-3">
        {section.section}
      </div>
      <div>
        {section.rows.map((r, i) => (
          <div
            key={i}
            className="flex items-center justify-between py-2 border-b last:border-0"
            style={{ borderColor: 'rgba(255,255,255,0.04)' }}
          >
            <span className="text-[12.5px] text-text-secondary">{r.label}</span>
            <span
              className="sw-mono text-[12.5px] font-semibold"
              style={{ color: r.accent || '#e2e8f0' }}
            >
              {r.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

const EDIT_SECTIONS = [
  { label: 'Sizing',  fields: [
    ['starting_capital', 'number', 'Starting Capital'],
    ['max_contracts',    'number', 'Max Contracts'],
    ['bp_pct',           'number', 'BP %'],
  ]},
  { label: 'Strategy', fields: [
    ['sd_mult',     'number',   'SD Multiplier'],
    ['delta_skew',  'number',   'Delta Skew'],
    ['use_gex_walls','checkbox','Use GEX Walls'],
  ]},
  { label: 'Exits',   fields: [
    ['pt_pct', 'number', 'Profit Take %'],
    ['sl_pct', 'number', 'Stop Loss %'],
  ]},
  { label: 'Schedule', fields: [
    ['entry_start_ct', 'text', 'Entry Start (CT)'],
    ['entry_end_ct',   'text', 'Entry End (CT)'],
    ['eod_close_ct',   'text', 'EOD Close (CT)'],
    ['entry_days',     'text', 'Entry Days (blank=all)'],
  ]},
  { label: 'Notifications', fields: [
    ['discord_alerts', 'checkbox', 'Discord Alerts'],
  ]},
];

function EditableForm({ cfg, onChange, onCancel, onSave, saving }) {
  return (
    <div className="px-5 py-5 grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-7">
      {EDIT_SECTIONS.map(section => (
        <div key={section.label} className="col-span-1">
          <div className="text-[10px] uppercase tracking-[0.16em] font-bold text-text-tertiary mb-3">
            {section.label}
          </div>
          <div className="space-y-3">
            {section.fields.map(([k, type, label]) => (
              <div key={k} className="flex items-center justify-between gap-3">
                <label className="text-[12.5px] text-text-secondary flex-1">{label}</label>
                {type === 'checkbox' ? (
                  <button
                    type="button"
                    onClick={() => onChange(k, !cfg[k])}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 ${
                      cfg[k] ? 'bg-accent' : 'bg-bg-hover ring-1 ring-border-default'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 rounded-full bg-white transition-transform duration-200 ${
                        cfg[k] ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                ) : (
                  <input
                    className="sw-input !w-32 !text-right"
                    type={type}
                    value={cfg[k] ?? ''}
                    onChange={e => onChange(
                      k,
                      type === 'number' ? Number(e.target.value) : e.target.value,
                    )}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="col-span-2 flex items-center justify-end gap-2 pt-2 border-t" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
        <button
          onClick={onCancel}
          className="px-3.5 py-2 rounded-md text-[12.5px] font-semibold sw-glass text-text-body hover:text-text-primary transition-colors"
          style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
        >
          Cancel
        </button>
        <button
          onClick={onSave}
          disabled={saving}
          className="px-3.5 py-2 rounded-md text-[12.5px] font-semibold text-white inline-flex items-center gap-1.5 disabled:opacity-60 hover:brightness-110 transition"
          style={{ background: '#0ea5e9' }}
        >
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </div>
  );
}

export default function ConfigTab({ bot }) {
  const [cfg, setCfg] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    botApi.config(bot).then(setCfg).catch(() => {});
  }, [bot]);

  function startEdit() {
    setDraft({ ...cfg });
    setEditing(true);
  }

  function cancelEdit() {
    setDraft(null);
    setEditing(false);
  }

  async function reload() {
    const next = await botApi.config(bot);
    setCfg(next);
  }

  function onChange(k, v) {
    setDraft(prev => ({ ...prev, [k]: v }));
  }

  async function onSave() {
    setSaving(true);
    try {
      const body = {};
      for (const section of EDIT_SECTIONS) {
        for (const [k] of section.fields) body[k] = draft[k];
      }
      const updated = await botApi.saveConfig(bot, body);
      setCfg(updated);
      setEditing(false);
      setDraft(null);
    } finally {
      setSaving(false);
    }
  }

  if (!cfg) {
    return <div className="text-text-tertiary text-[13px] py-8 text-center">Loading…</div>;
  }

  if (editing && draft) {
    return (
      <EditableForm
        cfg={draft}
        onChange={onChange}
        onCancel={cancelEdit}
        onSave={onSave}
        saving={saving}
      />
    );
  }

  const sections = buildSections(bot, cfg);
  return (
    <div className="px-5 py-5 grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-7">
      {sections.map((s, i) => (
        <ReadOnlySection key={i} section={s} />
      ))}
      <div className="col-span-2 flex items-center justify-end gap-2 pt-2">
        <button
          onClick={reload}
          className="px-3.5 py-2 rounded-md text-[12.5px] font-semibold sw-glass text-text-body hover:text-text-primary transition-colors"
          style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10), inset 0 1px 0 rgba(255,255,255,0.04)' }}
        >
          Reset
        </button>
        <button
          onClick={startEdit}
          className="px-3.5 py-2 rounded-md text-[12.5px] font-semibold text-white bg-blue-500 hover:bg-blue-600 inline-flex items-center gap-1.5"
        >
          <Pencil size={12} /> Edit configuration
        </button>
      </div>
    </div>
  );
}
