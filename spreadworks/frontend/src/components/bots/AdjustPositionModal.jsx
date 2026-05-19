import { useState } from 'react';
import { X } from 'lucide-react';
import { botApi } from '../../lib/botApi';

/**
 * Adjust the PT and/or SL dollar targets on an OPEN bot position.
 *
 * Why the modal exists: SL on every strategy and PT on TIDE/DRIFT are
 * stored as absolute $ on the position row, so editing them directly is
 * the cleanest way to retune a live trade without closing and reopening.
 * BREEZE / FLOW have a time-of-day PT ladder — submitting a PT here flips
 * pt_override=TRUE on the row so the ladder stops re-overriding it.
 */
export default function AdjustPositionModal({ bot, position, theme, onClose, onSaved }) {
  const initialPt = Number(position.pt_target_pnl ?? 0);
  const initialSl = Math.abs(Number(position.sl_target_pnl ?? 0));
  const maxProfit = position.max_profit != null ? Number(position.max_profit) : null;
  const maxLoss = position.max_loss != null ? Math.abs(Number(position.max_loss)) : null;
  const pnl = position.mtm_pnl != null ? Number(position.mtm_pnl) : 0;

  const [pt, setPt] = useState(initialPt.toFixed(2));
  const [sl, setSl] = useState(initialSl.toFixed(2));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const ptNum = parseFloat(pt);
  const slNum = parseFloat(sl);
  const ptValid = !Number.isNaN(ptNum) && ptNum >= 0;
  const slValid = !Number.isNaN(slNum) && slNum >= 0;
  const changed = ptValid && slValid && (ptNum !== initialPt || slNum !== initialSl);

  async function onSave() {
    if (!changed || saving) return;
    setSaving(true);
    setError(null);
    try {
      const body = {};
      if (ptNum !== initialPt) body.pt_target_pnl = ptNum;
      if (slNum !== initialSl) body.sl_target_pnl = slNum;
      await botApi.adjustPosition(bot, position.position_id, body);
      onSaved && onSaved();
      onClose && onClose();
    } catch (e) {
      setError(e.message || 'Save failed');
    }
    setSaving(false);
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(2,6,14,0.72)',
        backdropFilter: 'blur(6px)',
        display: 'grid', placeItems: 'center',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 440, maxWidth: 'calc(100vw - 32px)',
          background: 'rgba(13,28,46,0.95)',
          borderRadius: 14, padding: 22,
          boxShadow:
            'inset 0 0 0 1px rgba(125,211,252,0.14), inset 0 1px 0 rgba(255,255,255,0.05), 0 24px 60px -16px rgba(0,0,0,0.55)',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#fff' }}>Adjust position</div>
          <button
            onClick={onClose}
            style={{
              padding: 4, borderRadius: 6, background: 'transparent', color: '#94a3b8',
              border: 'none', cursor: 'pointer', display: 'grid', placeItems: 'center',
            }}
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
        <div style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: '#64748b', marginBottom: 18 }}>
          {position.position_id}
        </div>

        {/* PT input */}
        <Field
          label="Profit Target ($)"
          help={maxProfit ? `Max profit: $${maxProfit.toFixed(2)}` : null}
          value={pt}
          onChange={setPt}
          accentColor="#34d399"
          invalid={!ptValid}
        />

        {/* SL input */}
        <Field
          label="Stop Loss ($)"
          help={maxLoss ? `Max collateral at risk: $${maxLoss.toFixed(2)}` : null}
          value={sl}
          onChange={setSl}
          accentColor="#fb7185"
          invalid={!slValid}
        />

        {/* Current P&L hint */}
        <div
          style={{
            marginTop: 12,
            padding: '8px 12px',
            borderRadius: 8,
            background: 'rgba(125,211,252,0.06)',
            boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10)',
            fontSize: 11.5,
            color: '#94a3b8',
          }}
        >
          <span style={{ color: '#64748b' }}>Current P&amp;L: </span>
          <span style={{
            color: pnl >= 0 ? '#34d399' : '#fb7185',
            fontFamily: 'JetBrains Mono',
            fontWeight: 700,
          }}>
            {pnl >= 0 ? '+' : '−'}${Math.abs(pnl).toFixed(2)}
          </span>
        </div>

        {/* Override notice for IB / IC */}
        {(position.strategy === 'iron_butterfly' || position.strategy === 'iron_condor') &&
          parseFloat(pt) !== initialPt && (
          <div
            style={{
              marginTop: 10,
              padding: '8px 12px',
              borderRadius: 8,
              background: 'rgba(252,211,77,0.08)',
              boxShadow: 'inset 0 0 0 1px rgba(252,211,77,0.25)',
              fontSize: 11.5,
              color: '#fcd34d',
            }}
          >
            Editing PT here will override the time-of-day ladder for this position.
          </div>
        )}

        {error && (
          <div
            style={{
              marginTop: 10,
              padding: '8px 12px',
              borderRadius: 8,
              background: 'rgba(251,113,133,0.10)',
              boxShadow: 'inset 0 0 0 1px rgba(251,113,133,0.30)',
              fontSize: 12, color: '#fb7185',
            }}
          >
            {error}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 18 }}>
          <button
            onClick={onClose}
            style={{
              padding: '8px 14px', borderRadius: 6, fontSize: 12.5, fontWeight: 600,
              color: '#cbd5e1', background: 'rgba(7,16,28,0.55)',
              boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.10)',
              border: 'none', cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={!changed || saving}
            style={{
              padding: '8px 14px', borderRadius: 6, fontSize: 12.5, fontWeight: 700,
              color: theme.primary, background: theme.primarySoft,
              boxShadow: `inset 0 0 0 1px ${theme.primaryRing}`,
              border: 'none',
              cursor: !changed || saving ? 'not-allowed' : 'pointer',
              opacity: !changed || saving ? 0.45 : 1,
            }}
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, help, value, onChange, accentColor, invalid }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, color: accentColor,
          textTransform: 'uppercase', letterSpacing: '0.12em',
        }}>
          {label}
        </span>
        {help && (
          <span style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: '#64748b' }}>
            {help}
          </span>
        )}
      </div>
      <input
        type="number"
        step="0.01"
        min="0"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%',
          padding: '10px 12px',
          fontFamily: 'JetBrains Mono',
          fontSize: 14, fontWeight: 600,
          color: '#fff',
          background: 'rgba(7,16,28,0.55)',
          borderRadius: 8,
          border: 'none',
          outline: 'none',
          boxShadow: invalid
            ? 'inset 0 0 0 1px rgba(251,113,133,0.50)'
            : `inset 0 0 0 1px ${accentColor}40`,
        }}
      />
    </div>
  );
}
