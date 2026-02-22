"""Status card components for bot dashboards."""

from dash import html
import dash_bootstrap_components as dbc


def bot_status_card(status: dict, bot_name: str, color: str = "primary") -> dbc.Card:
    """Render a bot status overview card."""
    account = status.get("paper_account", {})
    pdt = status.get("pdt", {})

    balance = account.get("balance", 0)
    cumulative_pnl = account.get("cumulative_pnl", 0)
    return_pct = account.get("return_pct", 0)
    pnl_color = "success" if cumulative_pnl >= 0 else "danger"

    return dbc.Card([
        dbc.CardHeader(
            html.Div([
                html.H5(bot_name, className="mb-0 d-inline"),
                dbc.Badge(
                    status.get("strategy", ""),
                    color=color,
                    className="ms-2",
                ),
                dbc.Badge(
                    "ACTIVE" if status.get("is_active") else "INACTIVE",
                    color="success" if status.get("is_active") else "secondary",
                    className="ms-2",
                ),
            ]),
        ),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.P("Balance", className="text-muted mb-0 small"),
                    html.H4(f"${balance:,.2f}", className="mb-0"),
                ], width=4),
                dbc.Col([
                    html.P("P&L", className="text-muted mb-0 small"),
                    html.H4(
                        f"${cumulative_pnl:+,.2f}",
                        className=f"mb-0 text-{pnl_color}",
                    ),
                ], width=4),
                dbc.Col([
                    html.P("Return", className="text-muted mb-0 small"),
                    html.H4(
                        f"{return_pct:+.1f}%",
                        className=f"mb-0 text-{pnl_color}",
                    ),
                ], width=4),
            ], className="mb-3"),
            dbc.Row([
                dbc.Col([
                    html.Small("Open Positions", className="text-muted"),
                    html.Br(),
                    html.Strong(str(status.get("open_positions", 0))),
                ], width=3),
                dbc.Col([
                    html.Small("Today", className="text-muted"),
                    html.Br(),
                    html.Strong(
                        f"{status.get('trades_today', 0)}/"
                        f"{status.get('max_trades_per_day', 1)}"
                    ),
                ], width=3),
                dbc.Col([
                    html.Small("PDT Used", className="text-muted"),
                    html.Br(),
                    html.Strong(
                        f"{pdt.get('day_trades_rolling_5', 0)}/"
                        f"{status.get('pdt', {}).get('day_trades_remaining', 3) + pdt.get('day_trades_rolling_5', 0)}"
                    ),
                ], width=3),
                dbc.Col([
                    html.Small("Buying Power", className="text-muted"),
                    html.Br(),
                    html.Strong(f"${account.get('buying_power', 0):,.2f}"),
                ], width=3),
            ]),
        ]),
        dbc.CardFooter(
            html.Small(
                f"Last scan: {status.get('last_scan', 'Never')} | "
                f"VIX skip: {status.get('vix_skip', 32)} | "
                f"SD: {status.get('sd_multiplier', 1.2)}",
                className="text-muted",
            )
        ),
    ], className="mb-3")


def performance_card(stats: dict, bot_name: str) -> dbc.Card:
    """Render a performance statistics card."""
    pnl_color = "success" if stats.get("total_pnl", 0) >= 0 else "danger"

    return dbc.Card([
        dbc.CardHeader(html.H6(f"{bot_name} Performance", className="mb-0")),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.P("Win Rate", className="text-muted mb-0 small"),
                    html.H5(f"{stats.get('win_rate', 0):.1f}%"),
                ], width=3),
                dbc.Col([
                    html.P("Total P&L", className="text-muted mb-0 small"),
                    html.H5(
                        f"${stats.get('total_pnl', 0):+,.2f}",
                        className=f"text-{pnl_color}",
                    ),
                ], width=3),
                dbc.Col([
                    html.P("Avg Win", className="text-muted mb-0 small"),
                    html.H5(
                        f"${stats.get('avg_win', 0):+.2f}",
                        className="text-success",
                    ),
                ], width=3),
                dbc.Col([
                    html.P("Avg Loss", className="text-muted mb-0 small"),
                    html.H5(
                        f"${stats.get('avg_loss', 0):.2f}",
                        className="text-danger",
                    ),
                ], width=3),
            ]),
            html.Hr(),
            dbc.Row([
                dbc.Col([
                    html.Small("Trades", className="text-muted"),
                    html.Br(),
                    html.Strong(
                        f"{stats.get('wins', 0)}W / {stats.get('losses', 0)}L"
                    ),
                ], width=4),
                dbc.Col([
                    html.Small("Best", className="text-muted"),
                    html.Br(),
                    html.Strong(
                        f"${stats.get('best_trade', 0):+.2f}",
                        className="text-success",
                    ),
                ], width=4),
                dbc.Col([
                    html.Small("Worst", className="text-muted"),
                    html.Br(),
                    html.Strong(
                        f"${stats.get('worst_trade', 0):.2f}",
                        className="text-danger",
                    ),
                ], width=4),
            ]),
        ]),
    ], className="mb-3")
