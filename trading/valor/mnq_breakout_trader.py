"""Paper-forward adapter for the MNQ breakout, isolated from GEX/SAR exits.

Only the MNQ dispatch hooks invoke this mixin. Existing non-MNQ paths are unchanged.
No broker order function is called directly; the execution layer separately refuses
this source in live mode. Stops are deliberately absent, not falsely called zero risk.
"""
from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from threading import Lock

from . import mnq_breakout as strategy
from .models import FuturesSignal, SignalSource, TradeDirection, GammaRegime, PositionStatus, TradingMode, CENTRAL_TZ
from .integrity import serialized
from .db import db_connection

logger = logging.getLogger(__name__)


class MNQBreakoutMixin:
    _mnq_data_lock = Lock()

    @staticmethod
    def _is_mnq_breakout(position) -> bool:
        return (getattr(position, 'ticker', None) == 'MNQ' and
                getattr(getattr(position, 'signal_source', None), 'value', None) == strategy.SOURCE)

    def mnq_breakout_status(self):
        now = datetime.now(CENTRAL_TZ)
        enabled = os.getenv('VALOR_MNQ_BREAKOUT_PAPER_ENABLED', 'true').lower() in {'1', 'true', 'yes', 'on'}
        try:
            session = strategy.cash_session(now.date())
            flat_at = session[1].isoformat() if session else None
            window = strategy.entry_window(now)
        except strategy.InvalidMarketData:
            flat_at, window = None, False
        return dict(strategy=strategy.SOURCE, version=strategy.VERSION, enabled=enabled,
                    mode='paper_only', live_ready=False, live_orders_allowed=False,
                    active=enabled and self.config.mode == TradingMode.PAPER and 'MNQ' in self.config.tickers and 'MNQ' not in self.config.quarantined_tickers,
                    entry_window_open=window, today_flat_at=flat_at, max_hold_minutes=240,
                    lookback_minutes=30, contracts=1, max_positions=1, protective_stop=None,
                    sar=False, trailing=False, gex_used=False, probabilities_calibrated=False,
                    execution='observed bid/ask paper fills, not historical bar-open fills',
                    paper_fee_per_contract=self.config.paper_round_trip_fee,
                    extra_slippage_ticks=self.config.paper_slippage_ticks,
                    performance_filter='signal_source=MNQ_BREAKOUT_30M',
                    last_local_scan=getattr(self, '_mnq_last_scan_result', None))

    def _log_mnq(self, result, account_balance, quote=None, signal=None, evidence=None):
        self._mnq_last_scan_result = dict(result)
        q = quote or {}
        try:
            self.db.save_scan_activity(
                scan_id=result['scan_id'], ticker='MNQ', underlying_symbol='MNQ',
                outcome='TRADED' if result['trades_executed'] else 'NO_TRADE',
                action_taken=result['status'], decision_summary=result['status'],
                underlying_price=q.get('last', 0), bid_price=q.get('bid', 0), ask_price=q.get('ask', 0),
                signal_direction=signal.direction.value if signal else '', signal_source=strategy.SOURCE,
                signal_confidence=None, signal_win_probability=None, risk_amount=None,
                bayesian_alpha=None, bayesian_beta=None, bayesian_win_probability=None,
                positive_gamma_win_rate=None, negative_gamma_win_rate=None,
                signal_reasoning=signal.reasoning if signal else '', account_balance=account_balance,
                session_type='CASH_ONLY', is_overnight_session=not strategy.entry_window(datetime.now(CENTRAL_TZ)),
                trade_executed=bool(result['trades_executed']), position_id=result.get('position_id', ''),
                entry_price=signal.entry_price if signal else 0, stop_price=None,
                research_context=dict(strategy=self.mnq_breakout_status(), decision=evidence or {}, quote=q,
                                      code_commit=os.getenv('RENDER_GIT_COMMIT', 'unknown'),
                                      probabilities_not_applicable=True, risk_not_defined_by_stop=True))
        except Exception:
            logger.exception('MNQ breakout scan audit failed')

    def _run_mnq_breakout_scan(self, account_balance: float):
        import uuid
        now = datetime.now(CENTRAL_TZ)
        result = dict(timestamp=now.isoformat(), scan_id='MNQB-SCAN-'+uuid.uuid4().hex[:16], ticker='MNQ',
                      status='initializing', positions_checked=0, positions_closed=0,
                      signals_generated=0, trades_executed=0, errors=[])
        latest_quote = None
        def finish(status, quote=None, signal=None, evidence=None):
            result['status'] = status
            self._log_mnq(result, account_balance, quote or latest_quote, signal, evidence)
            return result
        # monitor_positions() also handles overdue exits and legacy positions.
        # Never fall back to GEX entries if the breakout feed is unavailable.
        info = self.mnq_breakout_status()
        if self.config.mode != TradingMode.PAPER:
            return finish('mnq_breakout_refuses_live_mode')
        if not info['enabled']:
            return finish('mnq_breakout_entries_paused')
        if 'MNQ' in self.config.quarantined_tickers:
            return finish('mnq_quarantined')
        latest_quote = self.executor.get_mes_quote(ticker='MNQ')
        if not info['entry_window_open']:
            return finish('outside_cash_session')
        positions = self.db.get_open_positions(ticker='MNQ')
        result['positions_checked'] = len(positions)
        if positions:
            return finish('one_position_limit_or_legacy_position')
        if not self._mnq_data_lock.acquire(blocking=False):
            return finish('mnq_data_fetch_in_progress')
        try:
            symbol = self.executor.get_entry_symbol('MNQ')
            if not strategy.contract_ok(symbol):
                return finish('no_exact_mnq_contract')
            boundary = now.replace(second=0, microsecond=0)
            cache_key = (symbol, boundary.isoformat())
            saved = getattr(self, '_mnq_candle_snapshot', None)
            if saved and saved[0] == cache_key:
                bars = saved[1]
            else:
                if getattr(self, '_mnq_fetch_attempt', None) == cache_key:
                    return finish('candle_retry_next_minute')
                self._mnq_fetch_attempt = cache_key
                bars = strategy.get_candles(self.executor, symbol, now)
                self._mnq_candle_snapshot = (cache_key, bars)
            decision = strategy.decide(bars, symbol, datetime.now(CENTRAL_TZ))
            if decision is None:
                return finish('no_completed_breakout_or_entry_window_expired')
            quote = self.executor.get_mes_quote(symbol=symbol, ticker='MNQ')
            if not quote or quote.get('contract_symbol') != symbol or not self.executor._quote_is_usable(quote):
                return finish('awaiting_fresh_exact_contract_quote')
            detail = decision.metadata()
            detail.update(observed_at=datetime.now(CENTRAL_TZ).isoformat(), candle_source='TASTYTRADE_DXLINK_CANDLE',
                          code_commit=os.getenv('RENDER_GIT_COMMIT', 'unknown'), raw_candles=bars)
            signal = FuturesSignal(ticker='MNQ', direction=TradeDirection.LONG if decision.side > 0 else TradeDirection.SHORT,
                confidence=0., source=SignalSource.MNQ_BREAKOUT_30M, current_price=quote['last'],
                gamma_regime=GammaRegime.NEUTRAL, gex_value=0., flip_point=0., call_wall=0., put_wall=0.,
                vix=0., atr=0., entry_price=quote['last'], contract_symbol=symbol,
                stop_price=0., target_price=0., contracts=1, win_probability=0.,
                stop_type='TIME_ONLY_PAPER', stop_points_used=0., reasoning=json.dumps(detail, allow_nan=False))
            result['signals_generated'] = 1
            success = self._execute_signal_internal(signal, account_balance, decision.key,
                                                    result['scan_id'], ticker='MNQ')
            if success:
                result['trades_executed'] = 1
                result['position_id'] = decision.key
                self.db.save_signal(signal, was_executed=True, ticker='MNQ')
            return finish('mnq_breakout_paper_opened' if success else 'entry_blocked_or_already_consumed', quote, signal, detail)
        except Exception as exc:
            result['errors'].append(type(exc).__name__)
            logger.error('MNQ breakout data/entry blocked: %s', type(exc).__name__)
            return finish('mnq_breakout_data_error')
        finally:
            self._mnq_data_lock.release()

    def _mnq_entry_permitted(self, signal, account_balance):
        """Called under the existing cross-process lifecycle lock."""
        if not self.mnq_breakout_status()['active']:
            return False
        if not strategy.paper_order_valid(signal, self.config.mode, datetime.now(CENTRAL_TZ)):
            return False
        positions = self.db.get_open_positions(ticker='MNQ')
        if positions or 'MNQ' not in self.config.tickers:
            return False
        from .models import get_ticker_config
        stats = self.db.get_ticker_performance_stats(['MNQ'])
        equity = get_ticker_config('MNQ').get('starting_capital', 100000.) + stats.get('MNQ', {}).get('total_pnl', 0.)
        allowed, _, quantity = self.margin_manager.can_open_position('MNQ', 1, positions, equity)
        return bool(allowed and quantity == 1 and account_balance > 0)

    def _manage_mnq_breakout(self, position, current_price):
        if self.config.mode != TradingMode.PAPER:
            logger.error('MNQ breakout paper position cannot be managed in live mode')
            return False
        self._update_position_high_low(position, current_price)
        try:
            detail = strategy.metadata(position.trade_reasoning, position.symbol)
            deadline = strategy.aware(detail['scheduled_exit'])
        except (ValueError, TypeError, KeyError):
            logger.error('MNQ breakout position metadata invalid: %s', position.position_id)
            return False
        now = datetime.now(CENTRAL_TZ)
        if now >= deadline:
            late = max(0, int((now-deadline).total_seconds()))
            return self._close_position(position, current_price, PositionStatus.CLOSED,
                                        f'MNQ_BREAKOUT_TIME_EXIT lateness_seconds={late}')
        return False

    @serialized
    def _close_mnq_breakout(self, position, price, status, reason):
        """Use existing paper fill/account transaction, without teaching the GEX model."""
        if self.config.mode != TradingMode.PAPER or not self._is_mnq_breakout(position):
            return False
        current = self.db.get_position_by_id(position.position_id)
        if current is None or current.status != PositionStatus.OPEN:
            return False
        success, _, fill = self.executor.close_position_order(current, reason, intended_close_price=price)
        if not success or fill is None or fill <= 0:
            logger.warning('MNQ timed exit awaiting a fresh quote: %s', current.position_id)
            return False
        closed, net = self.db.close_position(current.position_id, fill, reason, status, paper=True,
            paper_fill=dict(getattr(self.executor, 'last_paper_fill', None) or {}, fee_source=self.config.paper_fee_source),
            paper_fee=self.config.paper_round_trip_fee * current.contracts)
        if closed:
            self.daily_pnl += net
            self.daily_trades += 1
            if net < 0:
                self._daily_losses['MNQ'] = self._daily_losses.get('MNQ', 0.) + net
            self.db.log(level='INFO', action='MNQ_BREAKOUT_CLOSE', ticker='MNQ',
                        message=f'{strategy.VERSION} closed at {fill}',
                        details=dict(position_id=current.position_id, net=net, reason=reason, paper_only=True))
        return closed

    def mnq_breakout_performance(self):
        """Separate forward ledger; no historical backtest P&L is added to paper funds."""
        with db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute('''SELECT COUNT(*),COALESCE(SUM(realized_pnl),0),
                COUNT(*) FILTER (WHERE realized_pnl>0),MIN(open_time),MAX(close_time)
                FROM valor_closed_trades WHERE ticker='MNQ' AND signal_source=%s''', (strategy.SOURCE,))
            count, net, wins, first, last = cursor.fetchone()
        return dict(closed_trades=count, net_realized=float(net), wins=wins,
                    first_entry=first.isoformat() if first else None, last_exit=last.isoformat() if last else None,
                    source=strategy.SOURCE, paper_only=True)
