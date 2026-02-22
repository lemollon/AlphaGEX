"""
IronForge - Databricks Trading Dashboard
==========================================

Dash webapp for monitoring FLAME (2DTE) and SPARK (1DTE) Iron Condor bots.

Run locally:
    cd databricks
    python -m webapp.app

Or deploy as a Databricks App.
"""

import sys
import os
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

from webapp.layouts.flame_layout import flame_layout
from webapp.layouts.spark_layout import spark_layout
from webapp.layouts.compare_layout import compare_layout
from webapp.callbacks.flame_callbacks import register_flame_callbacks
from webapp.callbacks.spark_callbacks import register_spark_callbacks
from webapp.callbacks.compare_callbacks import register_compare_callbacks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)

# ============================================================================
# App setup
# ============================================================================

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="IronForge",
    update_title="IronForge | Loading...",
)

server = app.server  # For Databricks App deployment

# ============================================================================
# Navigation
# ============================================================================

navbar = dbc.Navbar(
    dbc.Container([
        dbc.NavbarBrand([
            html.Span("Iron", className="fw-bold"),
            html.Span("Forge", className="text-warning fw-bold"),
        ], href="/", className="fs-4"),
        dbc.Nav([
            dbc.NavItem(dbc.NavLink("FLAME", href="/flame", className="text-warning")),
            dbc.NavItem(dbc.NavLink("SPARK", href="/spark", className="text-primary")),
            dbc.NavItem(dbc.NavLink("Compare", href="/compare")),
        ], navbar=True),
    ], fluid=True),
    dark=True,
    color="dark",
    className="mb-4",
)

# ============================================================================
# Layout
# ============================================================================

app.layout = html.Div([
    dcc.Location(id="url", refresh=False),
    navbar,
    dbc.Container(id="page-content", fluid=True, className="px-4"),
])


@app.callback(
    dash.Output("page-content", "children"),
    dash.Input("url", "pathname"),
)
def display_page(pathname):
    """Route to the correct page layout."""
    if pathname == "/flame":
        return flame_layout()
    elif pathname == "/spark":
        return spark_layout()
    elif pathname == "/compare":
        return compare_layout()
    else:
        # Home page - overview
        return _home_layout()


def _home_layout():
    """Home page with quick overview of both bots."""
    return html.Div([
        html.Div([
            html.H1([
                html.Span("Iron", className="fw-bold"),
                html.Span("Forge", className="text-warning fw-bold"),
            ], className="display-4 text-center"),
            html.P(
                "FLAME vs SPARK Iron Condor Paper Trading on Databricks",
                className="lead text-center text-muted",
            ),
        ], className="mb-5 mt-3"),

        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H3("FLAME", className="text-warning text-center"),
                        html.H5("2DTE Iron Condor", className="text-muted text-center"),
                        html.Hr(),
                        html.P(
                            "Longer-duration Iron Condors with 2 days to "
                            "expiration. More premium, more time for the "
                            "trade to work.",
                            className="text-center",
                        ),
                        html.Div(
                            dbc.Button("View Dashboard", href="/flame", color="warning", outline=True),
                            className="text-center",
                        ),
                    ]),
                ], className="h-100"),
            ], md=4),

            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H3("SPARK", className="text-primary text-center"),
                        html.H5("1DTE Iron Condor", className="text-muted text-center"),
                        html.Hr(),
                        html.P(
                            "Shorter-duration Iron Condors with 1 day to "
                            "expiration. Faster theta decay, quicker "
                            "resolution.",
                            className="text-center",
                        ),
                        html.Div(
                            dbc.Button("View Dashboard", href="/spark", color="primary", outline=True),
                            className="text-center",
                        ),
                    ]),
                ], className="h-100"),
            ], md=4),

            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H3("Compare", className="text-center"),
                        html.H5("Head to Head", className="text-muted text-center"),
                        html.Hr(),
                        html.P(
                            "Side-by-side comparison of FLAME and SPARK. "
                            "Equity curves, win rates, P&L, and all "
                            "performance metrics.",
                            className="text-center",
                        ),
                        html.Div(
                            dbc.Button("View Comparison", href="/compare", color="light", outline=True),
                            className="text-center",
                        ),
                    ]),
                ], className="h-100"),
            ], md=4),
        ]),

        html.Hr(className="mt-5"),

        html.Div([
            html.H5("System Info", className="text-muted"),
            dbc.Row([
                dbc.Col([
                    html.Small("Platform", className="text-muted"),
                    html.Br(),
                    html.Strong("Databricks (Delta Lake)"),
                ], width=3),
                dbc.Col([
                    html.Small("Data Source", className="text-muted"),
                    html.Br(),
                    html.Strong("Tradier API (Production)"),
                ], width=3),
                dbc.Col([
                    html.Small("Ticker", className="text-muted"),
                    html.Br(),
                    html.Strong("SPY"),
                ], width=3),
                dbc.Col([
                    html.Small("Mode", className="text-muted"),
                    html.Br(),
                    dbc.Badge("PAPER", color="info"),
                ], width=3),
            ]),
        ], className="mt-3"),
    ])


# ============================================================================
# Register callbacks
# ============================================================================

register_flame_callbacks(app)
register_spark_callbacks(app)
register_compare_callbacks(app)

# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(debug=True, host="0.0.0.0", port=port)
