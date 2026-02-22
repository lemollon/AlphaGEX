"""Position and trade history table components."""

from dash import html, dash_table
import dash_bootstrap_components as dbc
from typing import List, Dict


def open_positions_table(positions: List[Dict]) -> html.Div:
    """Render open positions as a styled table."""
    if not positions:
        return dbc.Alert(
            "No open positions",
            color="secondary",
            className="text-center",
        )

    rows = []
    for pos in positions:
        pnl = pos.get("pnl_total")
        pnl_str = f"${pnl:+.2f}" if pnl is not None else "N/A"
        pnl_color = "text-success" if pnl and pnl >= 0 else "text-danger"

        rows.append(html.Tr([
            html.Td(pos.get("position_id", "")[:20]),
            html.Td(pos.get("expiration", "")),
            html.Td(
                f"{pos.get('put_long_strike', 0)}/{pos.get('put_short_strike', 0)}P-"
                f"{pos.get('call_short_strike', 0)}/{pos.get('call_long_strike', 0)}C"
            ),
            html.Td(f"x{pos.get('contracts', 0)}"),
            html.Td(f"${pos.get('entry_credit', 0):.2f}"),
            html.Td(
                f"${pos.get('current_cost_to_close', 0):.4f}"
                if pos.get("current_cost_to_close") is not None
                else "N/A"
            ),
            html.Td(pnl_str, className=pnl_color),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Position ID"),
            html.Th("Expiration"),
            html.Th("Strikes"),
            html.Th("Qty"),
            html.Th("Credit"),
            html.Th("Cost to Close"),
            html.Th("P&L"),
        ])),
        html.Tbody(rows),
    ], bordered=True, dark=True, hover=True, responsive=True, striped=True, size="sm")


def trade_history_table(trades: List[Dict]) -> html.Div:
    """Render closed trades as a styled table."""
    if not trades:
        return dbc.Alert(
            "No closed trades yet",
            color="secondary",
            className="text-center",
        )

    rows = []
    for trade in trades[:25]:  # Show last 25
        pnl = trade.get("realized_pnl", 0)
        pnl_color = "text-success" if pnl >= 0 else "text-danger"
        reason = trade.get("close_reason", "")

        reason_badge_color = {
            "profit_target": "success",
            "stop_loss": "danger",
            "eod_safety": "warning",
            "expired_previous_day": "info",
            "data_feed_failure": "dark",
        }.get(reason, "secondary")

        rows.append(html.Tr([
            html.Td(trade.get("close_time", "")[:16] if trade.get("close_time") else ""),
            html.Td(
                f"{trade.get('put_long_strike', 0)}/{trade.get('put_short_strike', 0)}P-"
                f"{trade.get('call_short_strike', 0)}/{trade.get('call_long_strike', 0)}C"
            ),
            html.Td(f"x{trade.get('contracts', 0)}"),
            html.Td(f"${trade.get('total_credit', 0):.2f}"),
            html.Td(f"${trade.get('close_price', 0):.4f}"),
            html.Td(f"${pnl:+.2f}", className=pnl_color),
            html.Td(dbc.Badge(reason, color=reason_badge_color, className="small")),
        ]))

    return dbc.Table([
        html.Thead(html.Tr([
            html.Th("Closed"),
            html.Th("Strikes"),
            html.Th("Qty"),
            html.Th("Credit"),
            html.Th("Close $"),
            html.Th("P&L"),
            html.Th("Reason"),
        ])),
        html.Tbody(rows),
    ], bordered=True, dark=True, hover=True, responsive=True, striped=True, size="sm")
