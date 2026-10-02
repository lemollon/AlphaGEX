#!/usr/bin/env python3
"""Offline, one-contract MES execution replay. Never imports the trading service.

Reuses selected production methods through AST extraction: importing trader.py
would load database/broker integrations. Only the explicitly allowlisted method
bodies are compiled; persistence and fills are replaced with in-memory adapters.
This is conditional on recorded signals, NOT a regeneration of historical GEX.
"""
from __future__ import annotations

import argparse
import ast
import copy
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "trading/valor/models.py"
spec = importlib.util.spec_from_file_location("valor_replay_models", MODEL_PATH)
models = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = models
spec.loader.exec_module(models)
CT = models.CENTRAL_TZ
UTC = timezone.utc
MINUTE = timedelta(minutes=1)

METHODS = {
    "trader.py": ("ValorTrader", (
        "_is_overnight_session", "_manage_position", "_manage_position_no_loss_trailing",
        "_update_position_high_low", "_execute_sar", "_check_stop_hit", "_check_profit_target_hit",
    )),
    "signals.py": ("ValorSignalGenerator", ("_set_stop_levels",)),
}


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Naive timestamp cannot be assigned a session safely")
    return result.astimezone(UTC)


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite numeric input")
    return result


def market_open(at):
    """Normal MES week; deliberately restricted to audited Sept 15–22 window."""
    local = at.astimezone(CT)
    return not (local.weekday() == 5 or
                (local.weekday() == 6 and local.hour < 17) or
                (local.weekday() == 4 and local.hour >= 16) or local.hour == 16)


class ReplayLog:
    def info(self, *args, **kwargs):
        pass

    debug = info
    warning = info

    def error(self, message, *args, **kwargs):
        # Production catches exceptions; offline validation must fail visibly.
        raise RuntimeError(message % args if args else message)


def production_rules(clock):
    namespace = dict(vars(models), datetime=clock, timedelta=timedelta, logger=ReplayLog())
    bodies, hashes = [], {}
    for filename, (class_name, wanted) in METHODS.items():
        path = ROOT / "trading/valor" / filename
        source = path.read_text()
        hashes[filename] = hashlib.sha256(source.encode()).hexdigest()
        tree = ast.parse(source)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
        found = {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}
        for name in wanted:
            node = copy.deepcopy(found[name])
            node.decorator_list = []  # No advisory-lock/database decorator offline.
            bodies.append(node)
    cls = ast.ClassDef(name="ProductionRules", bases=[], keywords=[], body=bodies, decorator_list=[])
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), cls], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), "<valor-production-rules>", "exec"), namespace)
    hashes["models.py"] = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    return namespace["ProductionRules"], hashes


def load_inputs(directory, start, end):
    bars = {}
    with gzip.open(directory / "MESZ6_1m.csv.gz", "rt") as handle:
        for row in csv.DictReader(handle):
            at = timestamp(row["time_utc"])
            if not start <= at < end:
                continue
            if row["contract"].lstrip("/") != "MESZ6":
                raise ValueError("Mixed contract candle file")
            values = tuple(number(row[k]) for k in ("open", "high", "low", "close"))
            o, h, low, c = values
            if at.second or at.microsecond or low <= 0 or not low <= min(o, c) <= max(o, c) <= h:
                raise ValueError("Malformed candle")
            if any(abs(v * 4 - round(v * 4)) > 1e-6 for v in values):
                raise ValueError("MES prices must be on the quarter-point grid")
            if at in bars:
                raise ValueError("Duplicate candle timestamp")
            if not market_open(at):
                raise ValueError("Candle during expected closure; review calendar")
            bars[at] = values
    if not bars:
        raise ValueError("No candles in requested window")
    missing = []
    at = start
    while at < end:
        if market_open(at) and at not in bars:
            missing.append(at.isoformat())
        at += MINUTE
    if missing:
        raise ValueError(f"{len(missing)} missing open-market minutes; first={missing[0]}")

    signals = defaultdict(list)
    counts = Counter()
    seen = set()
    with gzip.open(directory / "mes_scan_inputs.jsonl.gz", "rt") as handle:
        for line in handle:
            row = json.loads(line)
            at = timestamp(row["scan_time"])
            if not start <= at < end or row.get("signal_direction") not in ("LONG", "SHORT"):
                continue
            if row.get("underlying_symbol") not in ("MES", "/MESZ6", "MESZ6"):
                raise ValueError("Unexpected signal instrument")
            scan_id = row["scan_id"]
            if scan_id in seen:
                raise ValueError("Duplicate scan id")
            seen.add(scan_id)
            counts["directional_rows"] += 1
            # Earliest OHLC price known to occur AFTER the scan, never same-minute extrema.
            entry_at = at.replace(second=0, microsecond=0) + MINUTE
            if entry_at not in bars:
                counts["no_next_minute_bar"] += 1
                continue  # Do not queue a stale signal across a closure.
            signals[entry_at].append(row)
    for rows in signals.values():
        rows.sort(key=lambda r: (timestamp(r["scan_time"]), r["scan_id"]))
    return dict(sorted(bars.items())), signals, dict(counts)


def simulated_prices(bar, path, cadence):
    """Two hypothetical paths, NOT provable best/worst bounds from minute bars.

    Extrema assumed at seconds 20 and 40; production monitor samples every 15s.
    Optional 1s sensitivity changes observation frequency, not available evidence.
    No future extrema are put into MFE before that path reaches them.
    """
    o, h, low, c = bar
    knots = [(0, o), (20, h), (40, low), (60, c)] if path == "OHLC" else [(0, o), (20, low), (40, h), (60, c)]
    for second in range(0, 60, cadence):
        segment = min(second // 20, 2)
        a, av = knots[segment]
        b, bv = knots[segment + 1]
        yield second, round((av + (bv - av) * (second - a) / (b - a)) * 4) / 4


def make_engine(config, slippage, fee, sar, contract="/MESZ6"):
    class Clock:
        current = datetime(2026, 9, 15, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz or UTC)

    Rules, hashes = production_rules(Clock)

    class Engine(Rules):
        def __init__(self):
            self.config = copy.deepcopy(config)
            self.config.use_sar = sar
            if not self.config.use_no_loss_trailing:
                raise ValueError("This replay supports the deployed no-loss trailing mode only")
            self.db = self
            self.position = None
            self.last_event = None
            self.pause_until = None
            self.streak = 0
            self.daily_losses = defaultdict(float)
            self.trades = []
            self.counts = Counter()
            self.price = 0.0
            self.clock = Clock
            self.source_hashes = hashes
            self.entry_session = None
            self.signal_session = None
            self.max_drawdown = 0.0
            self.peak_equity = 0.0
            self.net = 0.0

        def get_position_by_id(self, position_id):
            return self.position if self.position and self.position.position_id == position_id else None

        def update_high_low_prices(self, *args, **kwargs):
            pass  # Production method has already mutated the in-memory position.

        def update_stop(self, *args, **kwargs):
            pass

        def entry_block(self, normal=True):
            if self.position:
                return "open_position"
            if self.last_event and (Clock.current - self.last_event).total_seconds() < max(60, self.config.entry_cooldown_seconds):
                return "cooldown"
            if "MES" in self.config.quarantined_tickers:
                return "quarantined"
            if self.daily_losses[Clock.current.astimezone(CT).date()] <= -2000:
                return "daily_loss_limit"
            if normal and self.pause_until and Clock.current < self.pause_until:
                return "loss_streak_pause"
            if normal and not self.config.trade_overnight and self._is_overnight_session():
                return "overnight_disabled"
            return None

        def _execute_signal_internal(self, signal, account_balance, position_id, scan_id="", ticker="MES"):
            # This adapter replaces broker execution; no database or broker exists here.
            is_sar = signal.source == models.SignalSource.SAR_REVERSAL
            block = self.entry_block(normal=not is_sar)
            if block:
                self.counts[("sar_blocked_" if is_sar else "entry_blocked_") + block] += 1
                return False
            sign = 1 if signal.direction == models.TradeDirection.LONG else -1
            fill = self.price + sign * slippage * .25
            if signal.stop_price <= 0 or fill <= 0:
                raise ValueError("Invalid order price")
            self.position = models.FuturesPosition(
                position_id=position_id, symbol=contract, ticker="MES", direction=signal.direction,
                contracts=1, entry_price=fill, entry_value=fill * 5,
                initial_stop=signal.stop_price, current_stop=signal.stop_price, breakeven_price=fill,
                open_time=Clock.current, high_price_since_entry=fill, low_price_since_entry=fill,
                gamma_regime=signal.gamma_regime, gex_value=signal.gex_value,
                flip_point=signal.flip_point, call_wall=signal.call_wall, put_wall=signal.put_wall,
                atr_at_entry=signal.atr, vix_at_entry=signal.vix,
                signal_source=signal.source, signal_confidence=signal.confidence,
                win_probability=signal.win_probability, stop_type=signal.stop_type,
                stop_points_used=signal.stop_points_used, scan_id=scan_id,
            )
            self.entry_session = "overnight" if self._is_overnight_session() else "rth"
            self.last_event = Clock.current
            self.counts["sar_entries" if is_sar else "signal_entries"] += 1
            return True

        def _close_position(self, position, close_price, status, reason):
            sign = 1 if position.direction == models.TradeDirection.LONG else -1
            # A software stop requests a market close; a gap cannot fill at an old trigger.
            fill = self.price - sign * slippage * .25
            gross = round(position.calculate_pnl(fill), 2)  # Slippage already in fills.
            net = round(gross - fee, 2)
            self.trades.append({
                "position_id": position.position_id, "scan_id": position.scan_id,
                "entry_utc": position.open_time.isoformat(), "exit_utc": Clock.current.isoformat(),
                "entry_session": self.entry_session, "signal_session": self.signal_session,
                "direction": position.direction.value, "entry_price": position.entry_price,
                "exit_price": fill, "requested_exit_price": close_price,
                "initial_stop": position.initial_stop, "stop_type": position.stop_type,
                "status": status.value, "reason": reason,
                "pnl_after_slippage_before_fees": gross, "fee": fee, "net_pnl": net,
            })
            self.counts["exit_" + status.value] += 1
            self.daily_losses[Clock.current.astimezone(CT).date()] += min(gross, 0)
            # Production streaks use fill P&L before fees, including zero as a loss.
            self.streak = 0 if gross > 0 else self.streak + 1
            if gross > 0:
                self.pause_until = None
            elif self.streak >= self.config.max_consecutive_losses:
                self.pause_until = Clock.current + timedelta(minutes=self.config.loss_streak_pause_minutes)
            self.net = round(self.net + net, 2)
            position.status = status
            self.position = None
            self.last_event = Clock.current
            return True

        def enter_recorded_signal(self, row):
            at = timestamp(row["scan_time"])
            hour = at.astimezone(CT).hour
            overnight = hour >= 15 or hour < 8
            self.signal_session = "overnight" if overnight else "rth"
            price = number(row["underlying_price"])
            if price <= 0:
                raise ValueError("Invalid recorded signal price")
            def context(key):
                return number(row.get(key) or 0)
            signal = models.FuturesSignal(
                ticker="MES", direction=models.TradeDirection(row["signal_direction"]),
                confidence=context("signal_confidence"), source=models.SignalSource(row["signal_source"]),
                current_price=price, entry_price=price,
                gamma_regime=models.GammaRegime(row.get("gamma_regime") or "NEUTRAL"),
                gex_value=context("gex_value"), flip_point=context("flip_point"),
                call_wall=context("call_wall"), put_wall=context("put_wall"),
                vix=context("vix"), atr=context("atr"), win_probability=context("signal_win_probability"),
            )
            signal, signal.stop_type, signal.stop_points_used = self._set_stop_levels(signal, signal.atr, overnight)
            return self._execute_signal_internal(signal, self.config.capital, str(row["scan_id"]), str(row["scan_id"]))

        def mark_equity(self):
            equity = self.net
            if self.position:
                sign = 1 if self.position.direction == models.TradeDirection.LONG else -1
                equity += self.position.calculate_pnl(self.price - sign * slippage * .25) - fee
            self.peak_equity = max(self.peak_equity, equity)
            self.max_drawdown = max(self.max_drawdown, self.peak_equity - equity)

    return Engine()


def statistics(trades):
    values = [t["net_pnl"] for t in trades]
    wins = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    return {"closed_trades": len(values), "net_closed_pnl": round(sum(values), 2),
            "expectancy": round(sum(values) / len(values), 2) if values else None,
            "win_rate_pct": round(100 * sum(v > 0 for v in values) / len(values), 2) if values else None,
            "profit_factor": round(wins / losses, 3) if losses else None}


def run_scenario(bars, signals, config, path, cadence, slippage, fee, sar):
    engine = make_engine(config, slippage, fee, sar)
    previous = None
    for at, bar in bars.items():
        if previous and at - previous > MINUTE and engine.position:
            engine.counts["positions_carried_across_closure"] += 1
        for second, price in simulated_prices(bar, path, cadence):
            engine.clock.current = at + timedelta(seconds=second)
            engine.price = price
            if engine.position:
                engine._manage_position(engine.position, price, ticker="MES")
            if second == 0:
                for row in signals.get(at, []):
                    # Avoid overwriting an active position's entry-session metadata.
                    block = engine.entry_block()
                    if block:
                        engine.counts["entry_blocked_" + block] += 1
                    else:
                        engine.enter_recorded_signal(row)
            engine.mark_equity()
        previous = at
    unresolved = None
    if engine.position:
        p = engine.position
        last_close = next(reversed(bars.values()))[3]
        unresolved = {"entry_utc": p.open_time.isoformat(), "entry_price": p.entry_price,
                      "direction": p.direction.value, "mark_to_last_close_before_exit_costs": round(p.calculate_pnl(last_close), 2)}
    report = {"sar_enabled": sar, "assumed_path": path, "monitor_seconds": cadence,
              "slippage_ticks_per_side": slippage, "round_trip_fee": fee,
              **statistics(engine.trades), "sampled_equity_drawdown": round(engine.max_drawdown, 2),
              "counts": dict(engine.counts), "unresolved_end_position": unresolved,
              "by_entry_session": {session: statistics([t for t in engine.trades if t["entry_session"] == session])
                                   for session in ("rth", "overnight")}}
    return report, engine.trades, engine.source_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--start", default="2026-09-15T00:00:00+00:00")
    parser.add_argument("--end", default="2026-09-22T12:42:00+00:00")
    parser.add_argument("--round-trip-fee", type=float, required=True, help="Per contract, excluding slippage")
    parser.add_argument("--fee-source", required=True, help="e.g. assumed, or broker statement date; no account numbers")
    parser.add_argument("--config", type=Path, help="Optional sanitized ValorConfig JSON; otherwise code defaults")
    parser.add_argument("--cadence", type=int, choices=(1, 15), default=15)
    args = parser.parse_args()
    start, end = timestamp(args.start), timestamp(args.end)
    if not timestamp("2026-09-15T00:00:00+00:00") <= start < end <= timestamp("2026-09-22T12:42:00+00:00"):
        raise ValueError("Calendar coverage is restricted to the audited Sept 15–22 window")
    if any(t.second or t.microsecond for t in (start, end)):
        raise ValueError("Window boundaries must be whole minutes")
    if not math.isfinite(args.round_trip_fee) or args.round_trip_fee < 0:
        raise ValueError("Invalid fees")
    config = models.ValorConfig.from_dict(json.loads(args.config.read_text())) if args.config else models.ValorConfig()
    bars, signals, counts = load_inputs(args.data_dir, start, end)
    # Unique output directory: never overwrite source research or a previous run.
    output = args.data_dir / ("valor_execution_" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir()
    scenarios = []
    for sar in (False, True):
        for path in ("OHLC", "OLHC"):
            for slip in (1, 2, 4):
                report, trades, hashes = run_scenario(bars, signals, config, path, args.cadence, slip, args.round_trip_fee, sar)
                name = f"sar_{int(sar)}_{path}_{slip}ticks.json.gz"
                with gzip.open(output / name, "wt") as handle:
                    json.dump(trades, handle, allow_nan=False)
                report["trade_file"] = name
                scenarios.append(report)
                sessions = report["by_entry_session"]
                print(f"SAR={sar} {path} {slip} ticks: {report['closed_trades']} trades, "
                      f"net ${report['net_closed_pnl']:.2f}; "
                      f"RTH ${sessions['rth']['net_closed_pnl']:.2f}, overnight ${sessions['overnight']['net_closed_pnl']:.2f}; "
                      f"SAR closes={report['counts'].get('exit_sar_closed', 0)}, "
                      f"reversals={report['counts'].get('sar_entries', 0)}", flush=True)
    used_config = {key: getattr(config, key) for key in (
        "use_no_loss_trailing", "use_sar", "no_loss_activation_pts", "no_loss_trail_distance",
        "no_loss_profit_target_pts", "max_unrealized_loss_pts", "sar_trigger_pts", "sar_mfe_threshold",
        "use_overnight_hybrid", "trade_overnight", "entry_cooldown_seconds", "max_consecutive_losses",
        "loss_streak_pause_minutes", "quarantined_tickers")}
    summary = {"test": "RECORDED-SIGNAL VALOR EXECUTION REPLAY", "production_ready": False,
               "contract": "/MESZ6", "start_utc": start.isoformat(), "end_exclusive_utc": end.isoformat(),
               "candles": len(bars), "signals": counts, "unexplained_missing_minutes": 0,
               "fee_source": args.fee_source, "config_source": str(args.config) if args.config else "current code defaults; not historical settings",
               "config": used_config, "mes_parameters": models.get_ticker_config("MES"),
               "source_sha256": hashes, "scenarios": scenarios,
               "limitations": [
                   "Recorded signals, not independent holdout or regenerated historical n+1 GEX decisions.",
                   "Historical signals lack exact contract identity; MESZ6 assignment is a period assumption.",
                   "One MES, initially flat; sizing, other instruments, margin and ML feedback are not replayed.",
                   "Two assumed intraminute paths are sensitivity scenarios, not guaranteed performance bounds.",
                   "15-second monitor is aligned to bar open; actual scheduler phase, delays and quotes are unknown.",
                   "Fees are caller supplied; spread/impact approximated by adverse slippage in both fills.",
                   "EOD job requests closes at 16:00 CT while market is closed. No executable quote evidence: positions carried to next open; EOD fills unverified.",
                   "Missing holiday calendar outside this explicitly restricted date window.",
                   "Unresolved final positions are marked separately, excluded from closed-trade metrics.",
                   "Full broker reconciliation, protective orders and forward paper verification remain live-readiness gates.",
               ]}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print("REPORT:", output / "summary.json")
    print("SAR and overnight execution replay complete. No broker access or database writes. Production readiness NOT certified.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"REPLAY STOPPED: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
