import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';
import { BOT_REGISTRY } from '../lib/botRegistry';

/**
 * Bundles every piece of data the Strategy Chart tab needs into one hook.
 *
 * Returns:
 *   {
 *     loading,
 *     error,
 *     position,   // first OPEN position (or null)
 *     payoff,     // pnl_curve + max_profit + max_loss + breakevens + pop
 *     candles,    // intraday OHLCV bars for the bot's ticker
 *     spot,       // latest underlying price
 *   }
 *
 * Auto-refreshes every `intervalMs` (default 15s). All four API calls
 * (positions, payoff, candles, spot) run in parallel.
 */
// Module-level cache keyed by bot id — re-mounting the Strategy Chart tab
// (or switching to a bot and back) hydrates from this immediately instead
// of waiting on the first refresh tick to paint.
const stratChartCache = new Map();

export function useStrategyChart(bot, intervalMs = 15000) {
  const meta = BOT_REGISTRY[bot];
  const ticker = meta?.ticker || 'SPY';

  const cached = stratChartCache.get(bot);
  const [state, setState] = useState(cached ?? {
    loading: true,
    error: null,
    position: null,
    payoff: null,
    candles: [],
    spot: null,
    ticker,
  });

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        // Fetch positions first — multi-ticker bots (UNDERTOW / DELTA) carry the
        // real underlying on the position itself, so the registry ticker may be
        // the placeholder 'multi'. Resolve the effective ticker before pulling
        // candles, otherwise we'd request candles for a symbol that has none.
        const posResp = await botApi.positions(bot);
        const open = (posResp.positions || []).find(p => p.status === 'OPEN')
          ?? (posResp.positions || [])[0]
          ?? null;
        const effectiveTicker = open?.ticker || ticker;

        // Candles for the effective ticker + payoff (if a position is on) run
        // in parallel.
        const [candlesResp, payoff] = await Promise.all([
          botApi.candles(effectiveTicker),
          open
            ? botApi.positionPayoff(bot, open.position_id).catch(() => null)
            : Promise.resolve(null),
        ]);

        if (cancelled) return;
        const next = {
          loading: false,
          error: null,
          position: open,
          payoff,
          candles: candlesResp.candles || [],
          spot: candlesResp.last_price ?? null,
          ticker: effectiveTicker,
        };
        stratChartCache.set(bot, next);
        setState(next);
      } catch (e) {
        if (cancelled) return;
        setState(prev => ({ ...prev, loading: false, error: e }));
      }
    }

    tick();
    const h = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot, intervalMs, ticker]);

  return state;
}
