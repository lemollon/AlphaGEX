"""Equity curve chart component."""

import plotly.graph_objects as go
from typing import List, Dict, Optional


def create_equity_chart(
    curve_data: List[Dict],
    title: str = "Equity Curve",
    starting_capital: float = 5000.0,
    color: str = "#3b82f6",
) -> go.Figure:
    """Create an equity curve chart from trade data."""
    fig = go.Figure()

    if not curve_data:
        fig.add_annotation(
            text="No closed trades yet",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="#6b7280"),
        )
        fig.update_layout(
            title=title,
            template="plotly_dark",
            height=350,
            paper_bgcolor="#1a1a2e",
            plot_bgcolor="#16213e",
        )
        return fig

    timestamps = [d["timestamp"] for d in curve_data]
    equities = [d["equity"] for d in curve_data]
    pnls = [d["pnl"] for d in curve_data]

    # Insert starting point
    timestamps.insert(0, timestamps[0])
    equities.insert(0, starting_capital)
    pnls.insert(0, 0)

    # Color equity line based on above/below starting capital
    fill_color = "rgba(16, 185, 129, 0.1)" if equities[-1] >= starting_capital else "rgba(239, 68, 68, 0.1)"

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=equities,
        mode="lines",
        name="Equity",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=fill_color,
    ))

    # Starting capital reference line
    fig.add_hline(
        y=starting_capital,
        line_dash="dot",
        line_color="#6b7280",
        annotation_text=f"Start: ${starting_capital:,.0f}",
        annotation_position="top left",
    )

    # Trade markers
    win_x = [timestamps[i + 1] for i, p in enumerate(pnls[1:]) if p > 0]
    win_y = [equities[i + 1] for i, p in enumerate(pnls[1:]) if p > 0]
    loss_x = [timestamps[i + 1] for i, p in enumerate(pnls[1:]) if p <= 0]
    loss_y = [equities[i + 1] for i, p in enumerate(pnls[1:]) if p <= 0]

    if win_x:
        fig.add_trace(go.Scatter(
            x=win_x, y=win_y,
            mode="markers",
            name="Win",
            marker=dict(color="#10b981", size=7, symbol="triangle-up"),
        ))

    if loss_x:
        fig.add_trace(go.Scatter(
            x=loss_x, y=loss_y,
            mode="markers",
            name="Loss",
            marker=dict(color="#ef4444", size=7, symbol="triangle-down"),
        ))

    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=350,
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        yaxis=dict(tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=20, t=60, b=40),
    )

    return fig


def create_comparison_chart(
    flame_data: List[Dict],
    spark_data: List[Dict],
    starting_capital: float = 5000.0,
) -> go.Figure:
    """Create a comparison equity chart overlaying FLAME and SPARK."""
    fig = go.Figure()

    for data, name, color in [
        (flame_data, "FLAME (2DTE)", "#f59e0b"),
        (spark_data, "SPARK (1DTE)", "#3b82f6"),
    ]:
        if not data:
            continue

        timestamps = [d["timestamp"] for d in data]
        equities = [d["equity"] for d in data]

        timestamps.insert(0, timestamps[0])
        equities.insert(0, starting_capital)

        fig.add_trace(go.Scatter(
            x=timestamps,
            y=equities,
            mode="lines",
            name=name,
            line=dict(color=color, width=2),
        ))

    fig.add_hline(
        y=starting_capital,
        line_dash="dot",
        line_color="#6b7280",
        annotation_text=f"Start: ${starting_capital:,.0f}",
        annotation_position="top left",
    )

    if not flame_data and not spark_data:
        fig.add_annotation(
            text="No closed trades yet for either bot",
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color="#6b7280"),
        )

    fig.update_layout(
        title="FLAME vs SPARK: Equity Comparison",
        template="plotly_dark",
        height=400,
        paper_bgcolor="#1a1a2e",
        plot_bgcolor="#16213e",
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        yaxis=dict(tickformat="$,.0f"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=60, r=20, t=60, b=40),
    )

    return fig
