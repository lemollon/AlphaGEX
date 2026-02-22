"""Callbacks for the SPARK dashboard."""

import logging

from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc

from trading.db import TradingDatabase
from trading.models import spark_config
from webapp.components.status_card import bot_status_card, performance_card
from webapp.components.equity_chart import create_equity_chart
from webapp.components.position_table import trade_history_table, open_positions_table

logger = logging.getLogger(__name__)

_config = spark_config()
_db = TradingDatabase(bot_name="SPARK", dte_mode="1DTE")


def _get_status() -> dict:
    from datetime import datetime
    from trading.models import CENTRAL_TZ

    account = _db.get_paper_account()
    open_positions = _db.get_open_positions()
    heartbeat = _db.get_heartbeat_info()
    today_str = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
    trades_today = _db.get_trades_today_count(today_str)
    pdt_count = _db.get_day_trade_count_rolling_5_days()

    return {
        "bot_name": "SPARK",
        "strategy": "1DTE Paper Iron Condor",
        "is_active": True,
        "ticker": "SPY",
        "dte": 1,
        "open_positions": len(open_positions),
        "trades_today": trades_today,
        "max_trades_per_day": 1,
        "profit_target_pct": _config.profit_target_pct,
        "stop_loss_pct": _config.stop_loss_pct,
        "vix_skip": _config.vix_skip,
        "sd_multiplier": _config.sd_multiplier,
        "last_scan": heartbeat.get("last_heartbeat") if heartbeat else "Never",
        "paper_account": account.to_dict(),
        "pdt": {
            "day_trades_rolling_5": pdt_count,
            "day_trades_remaining": max(0, _config.pdt_max_day_trades - pdt_count),
        },
    }


def register_spark_callbacks(app):
    """Register all SPARK dashboard callbacks."""

    @app.callback(
        Output("spark-status-card", "children"),
        Input("spark-refresh", "n_intervals"),
    )
    def update_status(_):
        try:
            status = _get_status()
            return bot_status_card(status, "SPARK", color="primary")
        except Exception as e:
            return dbc.Alert(f"Error loading status: {e}", color="danger")

    @app.callback(
        Output("spark-equity-chart", "children"),
        Input("spark-refresh", "n_intervals"),
    )
    def update_equity(_):
        try:
            curve = _db.get_equity_curve()
            fig = create_equity_chart(
                curve, title="SPARK Equity Curve", color="#3b82f6"
            )
            return dcc.Graph(figure=fig, config={"displayModeBar": False})
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("spark-performance-card", "children"),
        Input("spark-refresh", "n_intervals"),
    )
    def update_perf(_):
        try:
            stats = _db.get_performance_stats()
            return performance_card(stats, "SPARK")
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("spark-open-positions", "children"),
        Input("spark-refresh", "n_intervals"),
    )
    def update_positions(_):
        try:
            positions = _db.get_open_positions()
            if not positions:
                return dbc.Alert("No open positions", color="secondary")
            pos_dicts = [p.to_dict() for p in positions]
            return open_positions_table(pos_dicts)
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("spark-trade-history", "children"),
        Input("spark-refresh", "n_intervals"),
    )
    def update_trades(_):
        try:
            trades = _db.get_closed_trades(limit=25)
            return trade_history_table(trades)
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("spark-logs-table", "children"),
        Input("spark-refresh", "n_intervals"),
    )
    def update_logs(_):
        try:
            logs = _db.get_logs(limit=50)
            if not logs:
                return dbc.Alert("No logs yet", color="secondary")

            rows = []
            for log in logs:
                level_color = {
                    "TRADE_OPEN": "success",
                    "TRADE_CLOSE": "info",
                    "SKIP": "secondary",
                    "ERROR": "danger",
                    "RECOVERY": "warning",
                }.get(log.get("level", ""), "light")

                rows.append(html.Tr([
                    html.Td(log.get("timestamp", "")[:19]),
                    html.Td(dbc.Badge(log.get("level", ""), color=level_color)),
                    html.Td(log.get("message", ""), className="small"),
                ]))

            return dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Time"), html.Th("Level"), html.Th("Message"),
                ])),
                html.Tbody(rows),
            ], bordered=True, dark=True, hover=True, responsive=True, size="sm")
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")
