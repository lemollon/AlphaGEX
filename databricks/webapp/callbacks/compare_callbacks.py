"""Callbacks for the FLAME vs SPARK comparison view."""

import logging

from dash import html, dcc, callback, Output, Input
import dash_bootstrap_components as dbc

from trading.db import TradingDatabase
from webapp.components.status_card import bot_status_card, performance_card
from webapp.components.equity_chart import create_comparison_chart

logger = logging.getLogger(__name__)

_flame_db = TradingDatabase(bot_name="FLAME", dte_mode="2DTE")
_spark_db = TradingDatabase(bot_name="SPARK", dte_mode="1DTE")


def register_compare_callbacks(app):
    """Register comparison dashboard callbacks."""

    @app.callback(
        Output("compare-equity-chart", "children"),
        Input("compare-refresh", "n_intervals"),
    )
    def update_equity(_):
        try:
            flame_curve = _flame_db.get_equity_curve()
            spark_curve = _spark_db.get_equity_curve()
            fig = create_comparison_chart(flame_curve, spark_curve)
            return dcc.Graph(figure=fig, config={"displayModeBar": False})
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("compare-flame-status", "children"),
        Input("compare-refresh", "n_intervals"),
    )
    def update_flame_status(_):
        try:
            account = _flame_db.get_paper_account()
            return _mini_status(account, "FLAME", "warning")
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("compare-spark-status", "children"),
        Input("compare-refresh", "n_intervals"),
    )
    def update_spark_status(_):
        try:
            account = _spark_db.get_paper_account()
            return _mini_status(account, "SPARK", "primary")
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("compare-flame-perf", "children"),
        Input("compare-refresh", "n_intervals"),
    )
    def update_flame_perf(_):
        try:
            stats = _flame_db.get_performance_stats()
            return performance_card(stats, "FLAME")
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("compare-spark-perf", "children"),
        Input("compare-refresh", "n_intervals"),
    )
    def update_spark_perf(_):
        try:
            stats = _spark_db.get_performance_stats()
            return performance_card(stats, "SPARK")
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")

    @app.callback(
        Output("compare-metrics-table", "children"),
        Input("compare-refresh", "n_intervals"),
    )
    def update_metrics(_):
        try:
            flame_stats = _flame_db.get_performance_stats()
            spark_stats = _spark_db.get_performance_stats()

            metrics = [
                ("Total Trades", flame_stats.get("total_trades", 0), spark_stats.get("total_trades", 0)),
                ("Win Rate", f"{flame_stats.get('win_rate', 0):.1f}%", f"{spark_stats.get('win_rate', 0):.1f}%"),
                ("Total P&L", f"${flame_stats.get('total_pnl', 0):+,.2f}", f"${spark_stats.get('total_pnl', 0):+,.2f}"),
                ("Avg Win", f"${flame_stats.get('avg_win', 0):+.2f}", f"${spark_stats.get('avg_win', 0):+.2f}"),
                ("Avg Loss", f"${flame_stats.get('avg_loss', 0):.2f}", f"${spark_stats.get('avg_loss', 0):.2f}"),
                ("Best Trade", f"${flame_stats.get('best_trade', 0):+.2f}", f"${spark_stats.get('best_trade', 0):+.2f}"),
                ("Worst Trade", f"${flame_stats.get('worst_trade', 0):.2f}", f"${spark_stats.get('worst_trade', 0):.2f}"),
            ]

            rows = []
            for name, flame_val, spark_val in metrics:
                # Highlight the winner
                flame_class = ""
                spark_class = ""
                if name in ("Win Rate", "Total P&L", "Avg Win", "Best Trade"):
                    try:
                        fv = float(str(flame_val).replace("$", "").replace(",", "").replace("%", "").replace("+", ""))
                        sv = float(str(spark_val).replace("$", "").replace(",", "").replace("%", "").replace("+", ""))
                        if fv > sv:
                            flame_class = "text-success fw-bold"
                        elif sv > fv:
                            spark_class = "text-success fw-bold"
                    except (ValueError, TypeError):
                        pass

                rows.append(html.Tr([
                    html.Td(name, className="fw-bold"),
                    html.Td(str(flame_val), className=flame_class),
                    html.Td(str(spark_val), className=spark_class),
                ]))

            return dbc.Table([
                html.Thead(html.Tr([
                    html.Th("Metric"),
                    html.Th("FLAME (2DTE)", className="text-warning"),
                    html.Th("SPARK (1DTE)", className="text-primary"),
                ])),
                html.Tbody(rows),
            ], bordered=True, dark=True, hover=True, responsive=True, striped=True)
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger")


def _mini_status(account, name, color):
    """Minimal status display for comparison view."""
    pnl = account.cumulative_pnl
    pnl_color = "success" if pnl >= 0 else "danger"
    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Small("Balance", className="text-muted"),
                    html.H5(f"${account.balance:,.2f}"),
                ], width=4),
                dbc.Col([
                    html.Small("P&L", className="text-muted"),
                    html.H5(f"${pnl:+,.2f}", className=f"text-{pnl_color}"),
                ], width=4),
                dbc.Col([
                    html.Small("Return", className="text-muted"),
                    html.H5(f"{account.to_dict().get('return_pct', 0):+.1f}%", className=f"text-{pnl_color}"),
                ], width=4),
            ]),
        ]),
    ], className="mb-2")
