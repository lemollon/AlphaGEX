"""SPARK (1DTE) dashboard layout."""

from dash import html, dcc
import dash_bootstrap_components as dbc


def spark_layout() -> html.Div:
    """SPARK bot dashboard page."""
    return html.Div([
        html.H3([
            html.Span("SPARK", className="text-primary"),
            html.Small(" 1DTE Iron Condor", className="text-muted ms-2"),
        ], className="mb-3"),

        dcc.Interval(id="spark-refresh", interval=30_000, n_intervals=0),

        html.Div(id="spark-status-card"),

        dbc.Tabs([
            dbc.Tab(label="Equity Curve", tab_id="spark-equity", children=[
                html.Div(id="spark-equity-chart", className="mt-3"),
            ]),
            dbc.Tab(label="Performance", tab_id="spark-perf", children=[
                html.Div(id="spark-performance-card", className="mt-3"),
            ]),
            dbc.Tab(label="Positions", tab_id="spark-positions", children=[
                html.H5("Open Positions", className="mt-3"),
                html.Div(id="spark-open-positions"),
            ]),
            dbc.Tab(label="Trade History", tab_id="spark-history", children=[
                html.H5("Recent Trades", className="mt-3"),
                html.Div(id="spark-trade-history"),
            ]),
            dbc.Tab(label="Logs", tab_id="spark-logs", children=[
                html.Div(id="spark-logs-table", className="mt-3"),
            ]),
        ], active_tab="spark-equity", className="mt-3"),
    ])
