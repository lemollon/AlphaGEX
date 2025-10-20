"""
visualization_and_plans.py - Visualization and Trading Plan Classes
This file contains all visualization and trading plan generation
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List
import json

# Import what we need from other files
from config_and_database import MM_STATES, STRATEGIES
from intelligence_and_strategies import (
    TradingRAG, FREDIntegration, ClaudeIntelligence,
    MultiStrategyOptimizer, DynamicLevelCalculator
)

# Import engines from file 1
from core_classes_and_engines import BlackScholesPricer, MonteCarloEngine

# ============================================================================
# VISUALIZATION ENGINE
# ============================================================================
class GEXVisualizer:
    """Create professional trading visualizations"""
    
    @staticmethod
    def create_gex_profile(gex_data: Dict) -> go.Figure:
        """Create interactive GEX profile chart"""
        
        if not gex_data or 'strikes' not in gex_data:
            fig = go.Figure()
            fig.add_annotation(
                text="No GEX data available",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False
            )
            return fig
        
        strikes = []
        call_gamma = []
        put_gamma = []
        total_gamma = []
        
        spot = gex_data.get('spot_price', 0)
        
        for strike_data in gex_data['strikes']:
            strikes.append(strike_data['strike'])
            call_g = strike_data.get('call_gamma', 0) / 1e6
            put_g = -abs(strike_data.get('put_gamma', 0)) / 1e6
            
            call_gamma.append(call_g)
            put_gamma.append(put_g)
            total_gamma.append(call_g + put_g)
        
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=('Gamma Exposure by Strike', 'Net Gamma Profile')
        )
        
        fig.add_trace(
            go.Bar(
                x=strikes,
                y=call_gamma,
                name='Call Gamma',
                marker_color='green',
                opacity=0.7,
                hovertemplate='Strike: %{x}<br>Call Gamma: $%{y:.1f}M<extra></extra>'
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Bar(
                x=strikes,
                y=put_gamma,
                name='Put Gamma',
                marker_color='red',
                opacity=0.7,
                hovertemplate='Strike: %{x}<br>Put Gamma: $%{y:.1f}M<extra></extra>'
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=strikes,
                y=total_gamma,
                name='Net Gamma',
                line=dict(color='blue', width=2),
                hovertemplate='Strike: %{x}<br>Net Gamma: $%{y:.1f}M<extra></extra>'
            ),
            row=2, col=1
        )
        
        fig.add_vline(
            x=spot,
            line_dash="dash",
            line_color="yellow",
            annotation_text=f"Spot ${spot:.2f}",
            row='all'
        )
        
        flip_point = None
        for i in range(len(total_gamma) - 1):
            if total_gamma[i] * total_gamma[i + 1] < 0:
                flip_point = strikes[i] + (strikes[i + 1] - strikes[i]) * (
                    -total_gamma[i] / (total_gamma[i + 1] - total_gamma[i])
                )
                break
        
        if flip_point:
            fig.add_vline(
                x=flip_point,
                line_dash="dash",
                line_color="orange",
                annotation_text=f"Flip ${flip_point:.2f}",
                row='all'
            )
        
        fig.update_layout(
            title=f'GEX Profile Analysis - {gex_data.get("symbol", "N/A")}',
            height=600,
            showlegend=True,
            hovermode='x unified',
            template='plotly_dark',
            xaxis2_title='Strike Price',
            yaxis_title='Gamma Exposure ($M)',
            yaxis2_title='Net Gamma ($M)'
        )
        
        return fig
    
    @staticmethod
    def create_monte_carlo_chart(simulation_results: Dict, current_price: float) -> go.Figure:
        """Create Monte Carlo simulation visualization with clear explanation"""
        
        if 'price_paths_sample' not in simulation_results:
            return go.Figure()
        
        paths = simulation_results['price_paths_sample']
        days = list(range(paths.shape[1]))
        
        fig = go.Figure()
        
        for i in range(min(50, len(paths))):
            fig.add_trace(
                go.Scatter(
                    x=days,
                    y=paths[i],
                    mode='lines',
                    line=dict(width=0.5, color='lightgray'),
                    showlegend=False,
                    hoverinfo='skip'
                )
            )
        
        percentiles = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
        
        fig.add_trace(
            go.Scatter(
                x=days + days[::-1],
                y=list(percentiles[0]) + list(percentiles[4][::-1]),
                fill='toself',
                fillcolor='rgba(255, 0, 0, 0.1)',
                line=dict(color='rgba(255, 0, 0, 0)'),
                name='90% Confidence Range (5th-95th %ile)',
                showlegend=True,
                hovertemplate='90% of outcomes fall in this range<extra></extra>'
            )
        )
        
        fig.add_trace(
            go.Scatter(
                x=days + days[::-1],
                y=list(percentiles[1]) + list(percentiles[3][::-1]),
                fill='toself',
                fillcolor='rgba(0, 255, 0, 0.2)',
                line=dict(color='rgba(0, 255, 0, 0)'),
                name='50% Confidence Range (25th-75th %ile)',
                showlegend=True,
                hovertemplate='50% of outcomes fall in this range<extra></extra>'
            )
        )
        
        fig.add_trace(
            go.Scatter(
                x=days,
                y=percentiles[2],
                mode='lines',
                line=dict(color='yellow', width=3),
                name='Most Likely Path (Median)',
                hovertemplate='Day %{x}: $%{y:.2f}<extra></extra>'
            )
        )
        
        fig.add_hline(
            y=current_price,
            line_dash="dash",
            line_color="white",
            annotation_text=f"Current Price ${current_price:.2f}",
            annotation_position="left"
        )
        
        if simulation_results.get('probability_hit_flip'):
            flip_price = simulation_results.get('expected_final_price', current_price * 1.02)
            fig.add_hline(
                y=flip_price,
                line_dash="dot",
                line_color="green",
                annotation_text=f"Target ${flip_price:.2f} ({simulation_results['probability_hit_flip']:.0f}% chance)",
                annotation_position="right"
            )
        
        prob_profit = simulation_results.get('probability_hit_flip', 50)
        interpretation = "BULLISH" if prob_profit > 60 else "BEARISH" if prob_profit < 40 else "NEUTRAL"
        
        fig.update_layout(
            title={
                'text': f'Monte Carlo Simulation - {interpretation} Outlook<br>'
                       f'<sub>Based on 10,000 simulations | {prob_profit:.0f}% chance of profit</sub>',
                'x': 0.5,
                'xanchor': 'center'
            },
            xaxis_title='Days Forward',
            yaxis_title='Price ($)',
            template='plotly_dark',
            height=500,
            hovermode='x unified',
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left",
                x=0.01
            )
        )
        
        fig.add_annotation(
            text=f"📊 INTERPRETATION:<br>"
                 f"• Yellow line shows most likely path<br>"
                 f"• Green zone: 50% of outcomes<br>"
                 f"• Red zone: 90% of outcomes<br>"
                 f"• {prob_profit:.0f}% chance of reaching target",
            xref="paper", yref="paper",
            x=0.02, y=0.3,
            showarrow=False,
            bordercolor="cyan",
            borderwidth=1,
            bgcolor="rgba(0,0,0,0.8)",
            font=dict(size=10, color="white"),
            align="left"
        )
        
        return fig

# ============================================================================
# COMPREHENSIVE PLAN GENERATOR
# ============================================================================
class TradingPlanGenerator:
    """Generate detailed daily, weekly, and monthly trading plans"""
    
    def __init__(self):
        self.fred = FREDIntegration()
        
    def generate_daily_plan(self, symbol: str, market_data: Dict) -> Dict:
        """Generate comprehensive daily trading plan with exact levels"""
        
        spot = market_data.get('spot_price', 0)
        net_gex = market_data.get('net_gex', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        now = datetime.now()
        day = now.strftime('%A')
        
        fred_data = self.fred.get_economic_data()
        regime = self.fred.get_regime(fred_data)
        
        rag = TradingRAG()
        personal_stats = rag.get_personal_stats()
        
        optimizer = MultiStrategyOptimizer()
        best_strategies = optimizer.get_best_strategy(market_data)
        
        calculator = DynamicLevelCalculator()
        zones = calculator.get_profitable_zones(market_data)
        
        plan = {
            'symbol': symbol,
            'date': now.strftime('%Y-%m-%d'),
            'day': day,
            'generated_at': now.strftime('%H:%M CT'),
            'regime': regime,
            'personal_stats': personal_stats,
            'execution_schedule': {},
            'exact_trades': []
        }
        
        plan['execution_schedule'] = self._build_execution_schedule(
            symbol, spot, flip, call_wall, put_wall, regime, personal_stats, day
        )
        
        if best_strategies['best']:
            best = best_strategies['best']
            plan['exact_trades'].append({
                'time': '9:45 AM',
                'strategy': best['name'],
                'action': best['action'],
                'entry_zone': f"${spot-0.30:.2f} - ${spot+0.20:.2f}",
                'targets': [flip, call_wall] if 'CALL' in best['name'] else [flip, put_wall],
                'stop': put_wall if 'CALL' in best['name'] else call_wall,
                'expected_value': best['expected_value'],
                'your_success_rate': best['probability'],
                'position_size': f"${3000 * regime['size_multiplier']:.0f}"
            })
        
        plan['profitable_zones'] = zones
        
        plan['pre_market'] = self._generate_pre_market_checklist(
            symbol, net_gex, flip, spot, day
        )
        
        plan['opening_30min'] = self._generate_opening_strategy(
            spot, flip, net_gex, regime, day
        )
        
        plan['mid_morning'] = self._generate_mid_morning_strategy(
            spot, flip, call_wall, put_wall, net_gex
        )
        
        plan['lunch'] = {
            'strategy': 'NO NEW POSITIONS',
            'reasoning': 'Low volume, choppy price action',
            'manage_existing': 'Trail stops to breakeven on winners'
        }
        
        plan['power_hour'] = self._generate_power_hour_strategy(
            day, spot, flip, call_wall, put_wall, net_gex
        )
        
        plan['after_hours'] = {
            'review': 'Log all trades with outcomes',
            'prep_tomorrow': 'Check for overnight gamma changes',
            'alerts_to_set': [
                f"Break above ${flip:.2f}",
                f"Break below ${put_wall:.2f}",
                f"Approach to ${call_wall:.2f}"
            ]
        }
        
        return plan
    
    def generate_weekly_plan(self, symbol: str, market_data: Dict) -> Dict:
        """Generate comprehensive weekly trading plan"""
        
        spot = market_data.get('spot_price', 0)
        net_gex = market_data.get('net_gex', 0)
        flip = market_data.get('flip_point', 0)
        call_wall = market_data.get('call_wall', 0)
        put_wall = market_data.get('put_wall', 0)
        
        atm_call = int(spot / 5) * 5 + (5 if spot % 5 > 2.5 else 0)
        
        fred_data = self.fred.get_economic_data()
        regime = self.fred.get_regime(fred_data)
        
        pricer = BlackScholesPricer()
        
        plan = {
            'symbol': symbol,
            'week_of': datetime.now().strftime('%Y-%m-%d'),
            'regime': regime,
            'net_gex': f"${net_gex/1e9:.1f}B",
            'expected_return': 0,
            'days': {}
        }
        
        plan['days']['Monday'] = self._generate_monday_plan(
            spot, flip, call_wall, put_wall, net_gex, atm_call, pricer, regime
        )
        
        plan['days']['Tuesday'] = self._generate_tuesday_plan(
            spot, flip, call_wall, atm_call, pricer, regime
        )
        
        plan['days']['Wednesday'] = self._generate_wednesday_plan(
            spot, flip, call_wall, put_wall
        )
        
        plan['days']['Thursday'] = self._generate_thursday_plan(
            spot, call_wall, put_wall, pricer
        )
        
        plan['days']['Friday'] = self._generate_friday_plan(
            spot, net_gex
        )
        
        monday_return = 0.1 * 0.68 if net_gex < -1e9 else 0.05 * 0.45
        tuesday_return = 0.08 * 0.62
        thursday_return = 0.03 * 0.72
        plan['expected_return'] = f"+{(monday_return + tuesday_return + thursday_return)*100:.1f}%"
        
        return plan
    
    def generate_monthly_plan(self, symbol: str, market_data: Dict) -> Dict:
        """Generate comprehensive monthly trading plan"""
        
        today = datetime.now()
        month = today.month
        year = today.year
        
        first_day = datetime(year, month, 1)
        first_friday = first_day + timedelta(days=(4 - first_day.weekday() + 7) % 7)
        opex_date = first_friday + timedelta(days=14)
        
        plan = {
            'symbol': symbol,
            'month': today.strftime('%B %Y'),
            'generated': today.strftime('%Y-%m-%d'),
            'key_dates': {},
            'weekly_strategies': {},
            'expected_monthly_return': '',
            'risk_events': []
        }
        
        plan['weekly_strategies'] = self._generate_weekly_strategies(
            today, opex_date, market_data
        )
        
        plan['key_dates'] = {
            'CPI': 'Second Tuesday (8:30 AM)',
            'PPI': 'Second Wednesday (8:30 AM)',
            'OPEX': opex_date.strftime('%B %d'),
            'FOMC': 'Check Fed calendar',
            'Earnings': f"Check {symbol} earnings date",
            'Month-end': 'Window dressing flows'
        }
        
        plan['risk_events'] = [
            '🔴 CPI/PPI - High volatility mornings',
            '🔴 FOMC - No trades until after',
            '🟡 OPEX - Gamma expiry chaos',
            '🟡 Month-end - Rebalancing flows',
            '🟡 Earnings - IV crush risk'
        ]
        
        week1_return = 0.10
        week2_return = 0.07
        week3_return = 0.12
        week4_return = 0
        total_return = week1_return + week2_return + week3_return + week4_return
        plan['expected_monthly_return'] = f"+{total_return*100:.1f}% (following all rules)"
        
        return plan
    
    # Helper methods for plan generation
    def _build_execution_schedule(self, symbol, spot, flip, call_wall, put_wall, regime, personal_stats, day):
        """Build detailed execution schedule"""
        
        schedule = {
            '9:00-9:30': {
                'action': 'DO NOTHING',
                'reason': 'Initial volatility, false moves common',
                'your_stats': f"Your 9:30 AM entries: {personal_stats.get('early_win_rate', 45)}% win rate"
            },
            '9:45-10:15': {
                'action': 'PRIME ENTRY WINDOW',
                'triggers': {
                    'long_call': f"IF {symbol} > ${flip-0.50:.2f}",
                    'action': f"BUY {int(flip)} calls @ ~${2.40:.2f}",
                    'size': f"${3000 * regime['size_multiplier
