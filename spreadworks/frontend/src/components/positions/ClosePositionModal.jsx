import { useState } from 'react';

export default function ClosePositionModal({ position, onConfirm, onCancel }) {
  const [closePrice, setClosePrice] = useState('');

  const cp = parseFloat(closePrice) || 0;
  const realizedPnl = (position.entry_price - cp) * 100 * position.contracts;
  const pctOfMax = position.max_profit
    ? (realizedPnl / Math.abs(position.max_profit) * 100)
    : 0;

  const handleConfirm = () => {
    if (!closePrice || cp <= 0) return;
    onConfirm(position.id, cp);
  };

  const strat = position.strategy === 'double_diagonal' ? 'DD'
    : position.strategy === 'double_calendar' ? 'DC' : 'IC';

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-[1000] font-[var(--font-ui)] animate-fade-in"
      style={{ background: 'rgba(6, 6, 14, 0.8)', backdropFilter: 'blur(4px)' }}
      onClick={onCancel}
    >
      <div
        className="bg-bg-surface border border-border-default rounded-xl px-7 py-6 w-[400px] max-w-[90vw] text-text-primary text-[13px] shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="text-white font-bold text-base mb-2">Close Position</div>
        <div className="text-text-secondary text-xs mb-5 font-[var(--font-mono)] font-medium">
          {position.symbol} {strat} {position.long_put}/{position.short_put}/{position.short_call}/{position.long_call}
        </div>

        <label className="sw-label block mb-1.5">Enter debit to close (per contract)</label>
        <input
          type="number"
          step="0.01"
          min="0"
          placeholder="0.59"
          value={closePrice}
          onChange={(e) => setClosePrice(e.target.value)}
          className="sw-input w-full text-[15px] font-semibold mb-3.5"
          autoFocus
        />

        {closePrice && (
          <div className={`rounded-lg px-3.5 py-3 mb-4 text-[15px] font-bold font-[var(--font-mono)] text-center border ${
            realizedPnl >= 0
              ? 'bg-sw-green-dim border-sw-green/20 text-sw-green'
              : 'bg-sw-red-dim border-sw-red/20 text-sw-red'
          }`}>
            Realized P&L: {realizedPnl >= 0 ? '+' : ''}${realizedPnl.toFixed(2)}
            {position.max_profit ? ` (${pctOfMax >= 0 ? '+' : ''}${pctOfMax.toFixed(1)}% of max profit)` : ''}
          </div>
        )}

        <div className="flex gap-2.5">
          <button className="sw-btn-secondary flex-1 !py-2.5 !text-[13px]" onClick={onCancel}>Cancel</button>
          <button
            className={`sw-btn-danger flex-1 !py-2.5 !text-[13px] ${(!closePrice || cp <= 0) ? 'opacity-40 cursor-not-allowed' : ''}`}
            onClick={handleConfirm}
            disabled={!closePrice || cp <= 0}
          >
            Confirm Close
          </button>
        </div>
      </div>
    </div>
  );
}
