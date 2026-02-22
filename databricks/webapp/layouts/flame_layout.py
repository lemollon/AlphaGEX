"""FLAME (2DTE) dashboard layout."""

from dash import html, dcc
import dash_bootstrap_components as dbc


def flame_layout() -> html.Div:
    """FLAME bot dashboard page."""
    return html.Div([
        html.H3([
            html.Span("FLAME", className="text-warning"),
            html.Small(" 2DTE Iron Condor", className="text-muted ms-2"),
        ], className="mb-3"),

        # Auto-refresh
        dcc.Interval(id="flame-refresh", interval=30_000, n_intervals=0),

        # Status card
        html.Div(id="flame-status-card"),

        # Tabs
        dbc.Tabs([
            dbc.Tab(label="Equity Curve", tab_id="flame-equity", children=[
                html.Div(id="flame-equity-chart", className="mt-3"),
            ]),
            dbc.Tab(label="Performance", tab_id="flame-perf", children=[
                html.Div(id="flame-performance-card", className="mt-3"),
            ]),
            dbc.Tab(label="Positions", tab_id="flame-positions", children=[
                html.H5("Open Positions", className="mt-3"),
                html.Div(id="flame-open-positions"),
            ]),
            dbc.Tab(label="Trade History", tab_id="flame-history", children=[
                html.H5("Recent Trades", className="mt-3"),
                html.Div(id="flame-trade-history"),
            ]),
            dbc.Tab(label="Logs", tab_id="flame-logs", children=[
                html.Div(id="flame-logs-table", className="mt-3"),
            ]),
        ], active_tab="flame-equity", className="mt-3"),
    ])
