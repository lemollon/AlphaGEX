import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

const SECTIONS = [
  {
    label: 'ACCOUNT',
    fields: [
      ['starting_capital', 'number'],
      ['max_contracts', 'number'],
      ['bp_pct', 'number'],
    ],
  },
  {
    label: 'STRATEGY',
    fields: [
      ['sd_mult', 'number'],
      ['pt_pct', 'number'],
      ['sl_pct', 'number'],
      ['delta_skew', 'number'],
      ['use_gex_walls', 'checkbox'],
    ],
  },
  {
    label: 'SCHEDULE',
    fields: [
      ['entry_start_ct', 'text'],
      ['entry_end_ct', 'text'],
      ['eod_close_ct', 'text'],
    ],
  },
  {
    label: 'NOTIFICATIONS',
    fields: [
      ['discord_alerts', 'checkbox'],
    ],
  },
];

const FIELD_LABEL = {
  starting_capital: 'Starting Capital',
  max_contracts: 'Max Contracts',
  bp_pct: 'BP %',
  sd_mult: 'SD Multiplier',
  pt_pct: 'Profit Target %',
  sl_pct: 'Stop Loss %',
  delta_skew: 'Delta Skew',
  use_gex_walls: 'Use GEX Walls',
  entry_start_ct: 'Entry Start (CT)',
  entry_end_ct: 'Entry End (CT)',
  eod_close_ct: 'EOD Close (CT)',
  discord_alerts: 'Discord Alerts',
};

export default function ConfigTab({ bot }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { botApi.config(bot).then(setCfg).catch(() => {}); }, [bot]);

  if (!cfg) {
    return <div className="text-text-tertiary text-[13px] py-8 text-center">Loading…</div>;
  }

  function onChange(k, v) { setCfg(prev => ({ ...prev, [k]: v })); }

  async function onSave() {
    setSaving(true);
    try {
      const body = {};
      for (const section of SECTIONS) {
        for (const [k] of section.fields) body[k] = cfg[k];
      }
      const updated = await botApi.saveConfig(bot, body);
      setCfg(updated);
    } finally { setSaving(false); }
  }

  return (
    <div className="sw-card p-5">
      {SECTIONS.map((section, si) => (
        <div key={section.label}>
          {/* Section divider */}
          <div className="sw-section-divider text-text-muted mb-3 mt-2">
            <span>{section.label}</span>
            <span className="line bg-border-subtle" />
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            {section.fields.map(([k, type]) => (
              <div key={k}>
                <div className="sw-label mb-1.5">{(FIELD_LABEL[k] || k).toUpperCase()}</div>
                {type === 'checkbox' ? (
                  <button
                    type="button"
                    onClick={() => onChange(k, !cfg[k])}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 ${
                      cfg[k] ? 'bg-accent' : 'bg-bg-hover border border-border-default'
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
                    className="sw-input"
                    type={type}
                    value={cfg[k] ?? ''}
                    onChange={e =>
                      onChange(k, type === 'number' ? Number(e.target.value) : e.target.value)
                    }
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      <div className="flex justify-end mt-4 pt-4 border-t border-border-subtle">
        <button className="sw-btn-primary" onClick={onSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save Config'}
        </button>
      </div>
    </div>
  );
}
