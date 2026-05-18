import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

const FIELDS = [
  ['starting_capital','number'], ['max_contracts','number'],
  ['bp_pct','number'], ['sd_mult','number'],
  ['pt_pct','number'], ['sl_pct','number'],
  ['entry_start_ct','text'], ['entry_end_ct','text'], ['eod_close_ct','text'],
  ['delta_skew','number'],
  ['discord_alerts','checkbox'], ['use_gex_walls','checkbox'],
];

export default function ConfigTab({ bot }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { botApi.config(bot).then(setCfg).catch(()=>{}); }, [bot]);
  if (!cfg) return <div className="loading">Loading…</div>;

  function onChange(k, v) { setCfg(prev => ({ ...prev, [k]: v })); }
  async function onSave() {
    setSaving(true);
    try {
      const body = {};
      for (const [k] of FIELDS) body[k] = cfg[k];
      const updated = await botApi.saveConfig(bot, body);
      setCfg(updated);
    } finally { setSaving(false); }
  }

  return (
    <div className="config-form">
      {FIELDS.map(([k, type]) => (
        <div key={k} className="config-row">
          <label>{k}</label>
          {type === 'checkbox' ? (
            <input type="checkbox" checked={!!cfg[k]} onChange={e => onChange(k, e.target.checked)} />
          ) : (
            <input type={type} value={cfg[k] ?? ''}
                   onChange={e => onChange(k, type === 'number' ? Number(e.target.value) : e.target.value)} />
          )}
        </div>
      ))}
      <button onClick={onSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  );
}
