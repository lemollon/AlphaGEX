"""
Standard Deviation Level Tracking Component
Tracks how +/-1 and +/-7 std levels move compared to prior day
"""

import streamlit as st
from typing import Dict
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def display_std_level_changes(current_data: Dict, yesterday_data: Dict):
    """
    Display standard deviation level changes compared to prior day
    Shows if levels moved up, down, widened, or stayed the same
    """
    if not yesterday_data:
        st.info("📊 Need at least 2 days of data to show std level changes")
        return

    # Extract current std levels
    current_std_1_pos = current_data.get('std_1_pos', 0)
    current_std_1_neg = current_data.get('std_1_neg', 0)
    current_std_7_pos = current_data.get('std_7_pos', 0)
    current_std_7_neg = current_data.get('std_7_neg', 0)
    current_spot = current_data.get('spot_price', 0)

    # Extract yesterday std levels
    yesterday_std_1_pos = yesterday_data.get('std_1_pos', 0)
    yesterday_std_1_neg = yesterday_data.get('std_1_neg', 0)
    yesterday_std_7_pos = yesterday_data.get('std_7_pos', 0)
    yesterday_std_7_neg = yesterday_data.get('std_7_neg', 0)
    yesterday_spot = yesterday_data.get('spot_price', 0)

    # Calculate changes
    std_1_pos_change = current_std_1_pos - yesterday_std_1_pos
    std_1_neg_change = current_std_1_neg - yesterday_std_1_neg
    std_7_pos_change = current_std_7_pos - yesterday_std_7_pos
    std_7_neg_change = current_std_7_neg - yesterday_std_7_neg

    # Calculate range widths
    current_1std_width = current_std_1_pos - current_std_1_neg
    yesterday_1std_width = yesterday_std_1_pos - yesterday_std_1_neg
    current_7std_width = current_std_7_pos - current_std_7_neg
    yesterday_7std_width = yesterday_std_7_pos - yesterday_std_7_neg

    width_1std_change = current_1std_width - yesterday_1std_width
    width_7std_change = current_7std_width - yesterday_7std_width

    # Display header
    st.subheader("📏 Standard Deviation Level Movement (Day-over-Day)")

    # Create 2x2 grid
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### +1 STD Level")
        delta_color = "normal" if abs(std_1_pos_change) < 0.01 else "off"
        direction = "↑" if std_1_pos_change > 0 else "↓" if std_1_pos_change < 0 else "→"
        st.metric(
            "Current +1σ",
            f"${current_std_1_pos:.2f}",
            delta=f"{direction} ${abs(std_1_pos_change):.2f}",
            delta_color=delta_color
        )

        st.markdown("### -1 STD Level")
        direction = "↑" if std_1_neg_change > 0 else "↓" if std_1_neg_change < 0 else "→"
        st.metric(
            "Current -1σ",
            f"${current_std_1_neg:.2f}",
            delta=f"{direction} ${abs(std_1_neg_change):.2f}",
            delta_color=delta_color
        )

    with col2:
        st.markdown("### +7 STD Level")
        delta_color = "normal" if abs(std_7_pos_change) < 0.01 else "off"
        direction = "↑" if std_7_pos_change > 0 else "↓" if std_7_pos_change < 0 else "→"
        st.metric(
            "Current +7σ",
            f"${current_std_7_pos:.2f}",
            delta=f"{direction} ${abs(std_7_pos_change):.2f}",
            delta_color=delta_color
        )

        st.markdown("### -7 STD Level")
        direction = "↑" if std_7_neg_change > 0 else "↓" if std_7_neg_change < 0 else "→"
        st.metric(
            "Current -7σ",
            f"${current_std_7_neg:.2f}",
            delta=f"{direction} ${abs(std_7_neg_change):.2f}",
            delta_color=delta_color
        )

    # Show range width changes
    st.markdown("---")
    st.markdown("### 📐 Range Width Analysis")

    range_col1, range_col2 = st.columns(2)

    with range_col1:
        width_direction = "WIDENED" if width_1std_change > 0 else "NARROWED" if width_1std_change < 0 else "UNCHANGED"
        width_color = "🟢" if width_1std_change > 0 else "🔴" if width_1std_change < 0 else "⚪"
        st.metric(
            "1σ Range Width",
            f"${current_1std_width:.2f}",
            delta=f"{width_color} {width_direction} ${abs(width_1std_change):.2f}"
        )

    with range_col2:
        width_direction = "WIDENED" if width_7std_change > 0 else "NARROWED" if width_7std_change < 0 else "UNCHANGED"
        width_color = "🟢" if width_7std_change > 0 else "🔴" if width_7std_change < 0 else "⚪"
        st.metric(
            "7σ Range Width",
            f"${current_7std_width:.2f}",
            delta=f"{width_color} {width_direction} ${abs(width_7std_change):.2f}"
        )

    # Trading interpretation
    st.markdown("---")
    st.markdown("### 💡 Trading Interpretation")

    interpretation = []

    if width_1std_change > 0:
        interpretation.append("✓ **Expanding 1σ range** = Increasing short-term volatility, expect wider price swings")
    elif width_1std_change < 0:
        interpretation.append("✓ **Contracting 1σ range** = Decreasing volatility, good for premium selling")

    if width_7std_change > 0:
        interpretation.append("✓ **Expanding 7σ range** = Increasing longer-term volatility expectations")
    elif width_7std_change < 0:
        interpretation.append("✓ **Contracting 7σ range** = Market settling down, volatility compression")

    # Check if both levels moved in same direction (shift)
    if std_1_pos_change > 0 and std_1_neg_change > 0:
        interpretation.append("✓ **1σ shifted UP** = Bullish bias, expected range moved higher")
    elif std_1_pos_change < 0 and std_1_neg_change < 0:
        interpretation.append("✓ **1σ shifted DOWN** = Bearish bias, expected range moved lower")

    if std_7_pos_change > 0 and std_7_neg_change > 0:
        interpretation.append("✓ **7σ shifted UP** = Long-term bullish outlook")
    elif std_7_pos_change < 0 and std_7_neg_change < 0:
        interpretation.append("✓ **7σ shifted DOWN** = Long-term bearish outlook")

    for item in interpretation:
        st.markdown(item)

    # Visual chart
    create_std_movement_chart(current_data, yesterday_data)


def create_std_movement_chart(current_data: Dict, yesterday_data: Dict):
    """Create visual chart showing std level movements"""

    fig = go.Figure()

    # Extract data
    current_std_1_pos = current_data.get('std_1_pos', 0)
    current_std_1_neg = current_data.get('std_1_neg', 0)
    current_std_7_pos = current_data.get('std_7_pos', 0)
    current_std_7_neg = current_data.get('std_7_neg', 0)
    current_spot = current_data.get('spot_price', 0)

    yesterday_std_1_pos = yesterday_data.get('std_1_pos', 0)
    yesterday_std_1_neg = yesterday_data.get('std_1_neg', 0)
    yesterday_std_7_pos = yesterday_data.get('std_7_pos', 0)
    yesterday_std_7_neg = yesterday_data.get('std_7_neg', 0)
    yesterday_spot = yesterday_data.get('spot_price', 0)

    # Add yesterday levels (lighter colors)
    fig.add_hline(
        y=yesterday_std_7_pos, line_dash="dot", line_color="rgba(255, 0, 0, 0.3)",
        annotation_text=f"Yesterday +7σ: ${yesterday_std_7_pos:.2f}", annotation_position="left"
    )
    fig.add_hline(
        y=yesterday_std_1_pos, line_dash="dot", line_color="rgba(255, 165, 0, 0.3)",
        annotation_text=f"Yesterday +1σ: ${yesterday_std_1_pos:.2f}", annotation_position="left"
    )
    fig.add_hline(
        y=yesterday_spot, line_dash="dot", line_color="rgba(255, 255, 255, 0.3)",
        annotation_text=f"Yesterday Spot: ${yesterday_spot:.2f}", annotation_position="right"
    )
    fig.add_hline(
        y=yesterday_std_1_neg, line_dash="dot", line_color="rgba(0, 255, 0, 0.3)",
        annotation_text=f"Yesterday -1σ: ${yesterday_std_1_neg:.2f}", annotation_position="left"
    )
    fig.add_hline(
        y=yesterday_std_7_neg, line_dash="dot", line_color="rgba(0, 0, 255, 0.3)",
        annotation_text=f"Yesterday -7σ: ${yesterday_std_7_neg:.2f}", annotation_position="left"
    )

    # Add current levels (solid, bright colors)
    fig.add_hline(
        y=current_std_7_pos, line_dash="solid", line_color="red", line_width=3,
        annotation_text=f"Current +7σ: ${current_std_7_pos:.2f}", annotation_position="right"
    )
    fig.add_hline(
        y=current_std_1_pos, line_dash="solid", line_color="orange", line_width=3,
        annotation_text=f"Current +1σ: ${current_std_1_pos:.2f}", annotation_position="right"
    )
    fig.add_hline(
        y=current_spot, line_dash="solid", line_color="white", line_width=4,
        annotation_text=f"Current Spot: ${current_spot:.2f}", annotation_position="right"
    )
    fig.add_hline(
        y=current_std_1_neg, line_dash="solid", line_color="lime", line_width=3,
        annotation_text=f"Current -1σ: ${current_std_1_neg:.2f}", annotation_position="right"
    )
    fig.add_hline(
        y=current_std_7_neg, line_dash="solid", line_color="cyan", line_width=3,
        annotation_text=f"Current -7σ: ${current_std_7_neg:.2f}", annotation_position="right"
    )

    # Add shaded zones
    fig.add_hrect(y0=current_std_1_neg, y1=current_std_1_pos, fillcolor="green", opacity=0.1, annotation_text="1σ Range")
    fig.add_hrect(y0=current_std_7_neg, y1=current_std_7_pos, fillcolor="blue", opacity=0.05, annotation_text="7σ Range")

    fig.update_layout(
        title="Standard Deviation Levels: Today vs Yesterday",
        height=600,
        template='plotly_dark',
        yaxis_title="Price ($)",
        xaxis=dict(showticklabels=False, showgrid=False),
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True, key="std_level_changes_chart")
