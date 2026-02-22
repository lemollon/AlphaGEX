"""FLAME vs SPARK comparison layout."""

from dash import html, dcc
import dash_bootstrap_components as dbc


def compare_layout() -> html.Div:
    """Side-by-side comparison of FLAME and SPARK performance."""
    return html.Div([
        html.H3([
            html.Span("FLAME", className="text-warning"),
            html.Span(" vs ", className="text-muted"),
            html.Span("SPARK", className="text-primary"),
            html.Small(" — 2DTE vs 1DTE Comparison", className="text-muted ms-2"),
        ], className="mb-3"),

        dcc.Interval(id="compare-refresh", interval=60_000, n_intervals=0),

        # Combined equity chart
        html.Div(id="compare-equity-chart"),

        html.Hr(),

        # Side-by-side status cards
        dbc.Row([
            dbc.Col([
                html.H5("FLAME (2DTE)", className="text-warning"),
                html.Div(id="compare-flame-status"),
                html.Div(id="compare-flame-perf"),
            ], md=6),
            dbc.Col([
                html.H5("SPARK (1DTE)", className="text-primary"),
                html.Div(id="compare-spark-status"),
                html.Div(id="compare-spark-perf"),
            ], md=6),
        ], className="mt-3"),

        html.Hr(),

        # Comparison metrics table
        html.H5("Head-to-Head Metrics"),
        html.Div(id="compare-metrics-table", className="mt-2"),
    ])
