import { useState } from 'react';
import { STRAT_LABELS, isCreditStrategy } from '../../lib/strategies';

export default function ClosePositionModal({ position, onConfirm, onCancel }) {
  const [closePrice, setClosePrice] = useState('');
  const isCredit = isCreditStrategy(position.strategy);
  const isExpired = position.dte != null && position.dte <= 0;

  const cp = parseFloat(closePrice) || 0;
  const realizedPnl = isCredit
    ? (position.entry_price - cp) * 100 * position.contracts
    : -(cp + position.entry_price) * 100 * position.contracts;

  // Cap preview at max profit/max loss
  const cappedPnl = position.max_profit != null
    ? Math.min(realizedPnl, Math.abs(position.max_profit))
    : realizedPnl;
  const displayPnl = position.max_loss != null
    ? Math.max(cappedPnl, -Math.abs(position.max_loss))
    : cappedPnl;

  const handleConfirm = () => {
    if (closePrice === '' && !isExpired) return;
    onConfirm(position.id, cp);
  };

  const handleExpireWorthless = () => {
    onConfirm(position.id, 0);
  };

  const strat = STRAT_LABELS[position.strategy] || position.strategy;

  // Preview for expire worthless
  const worthlessPnl = isCredit
    ? position.entry_price * 100 * position.contracts
    : -(position.entry_price) * 100 * position.contracts;
  const cappedWorthless = position.max_profit != null
    ? Math.min(worthlessPnl, Math.abs(position.max_profit))
    : worthlessPnl;
  const displayWorthless = position.max_loss != null
    ? Math.max(cappedWorthless, -Math.abs(position.max_loss))
    : cappedWorthless;

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
        <div className="text-white font-bold text-base mb-2">
          {isExpired ? 'Close Expired Position' : 'Close Position'}
        </div>
        <div className="text-text-secondary text-xs mb-5 font-[var(--font-mono)] font-medium">
          {position.symbol} {strat} {position.long_put}/{position.short_put}/{position.short_call}/{position.long_call}
        </div>

        {/* Expire Worthless option */}
        {isExpired && (
          <div className="mb-4">
            <div className={`rounded-lg px-3.5 py-3 mb-2.5 text-center border ${
              displayWorthless >= 0
                ? 'bg-sw-green-dim border-sw-green/20'
                : 'bg-sw-red-dim border-sw-red/20'
            }`}>
              <div className="text-text-secondary text-[11px] mb-1 font-medium">Expired Worthless P&L</div>
              <div className={`text-[15px] font-bold font-[var(--font-mono)] ${displayWorthless >= 0 ? 'text-sw-green' : 'text-sw-red'}`}>
                {displayWorthless >= 0 ? '+' : ''}${displayWorthless.toFixed(2)}
                {isCredit ? ' (full credit kept)' : ' (full debit lost)'}
              </div>
            </div>
            <button
              className="w-full sw-btn-danger !py-2.5 !text-[13px] font-semibold"
              onClick={handleExpireWorthless}
            >
              Expire Worthless ($0.00)
            </button>
            <div className="text-center text-text-muted text-[11px] mt-2.5 mb-3">
              — or enter a custom close price below —
            </div>
          </div>
        )}

        <label className="sw-label block mb-1.5">
          {isCredit ? 'Enter debit to close (per share)' : 'Enter spread value to close (per share)'}
        </label>
        <input
          type="number"
          step="0.01"
          min="0"
          placeholder="0.59"
          value={closePrice}
          onChange={(e) => setClosePrice(e.target.value)}
          className="sw-input w-full text-[15px] font-semibold mb-3.5"
          autoFocus={!isExpired}
        />

        {closePrice && (
          <div className={`rounded-lg px-3.5 py-3 mb-4 text-[15px] font-bold font-[var(--font-mono)] text-center border ${
            displayPnl >= 0
              ? 'bg-sw-green-dim border-sw-green/20 text-sw-green'
              : 'bg-sw-red-dim border-sw-red/20 text-sw-red'
          }`}>
            Realized P&L: {displayPnl >= 0 ? '+' : ''}${displayPnl.toFixed(2)}
            {position.max_profit ? ` (${(displayPnl / Math.abs(position.max_profit) * 100).toFixed(1)}% of max)` : ''}
          </div>
        )}

        <div className="flex gap-2.5">
          <button className="sw-btn-secondary flex-1 !py-2.5 !text-[13px]" onClick={onCancel}>Cancel</button>
          <button
            className={`sw-btn-danger flex-1 !py-2.5 !text-[13px] ${(closePrice === '' || cp < 0) ? 'opacity-40 cursor-not-allowed' : ''}`}
            onClick={handleConfirm}
            disabled={closePrice === '' || cp < 0}
          >
            Close at ${cp.toFixed(2)}
          </button>
        </div>
      </div>
    </div>
  );
}
