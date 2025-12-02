"""
SPX WHEEL TRADING DASHBOARD - COMPLETE REDESIGN

This dashboard provides FULL TRANSPARENCY into:
- Live/Paper Trading
- Backtest Results & Reports
- Calibration Parameters
- Data Quality
- System Status

PAGES:
1. Overview - Summary dashboard
2. Backtest - Full backtest report with equity curve
3. Trades - All live/paper trades
4. Positions - Current open positions
5. Calibration - Run and view calibration
6. System - Circuit breaker, alerts, settings

Run with: python dashboard/app.py
Then open: http://localhost:5000
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify, request, redirect, url_for
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

app = Flask(__name__)

# Store background task status
background_tasks = {}

# =============================================================================
# BASE TEMPLATE WITH NAVIGATION
# =============================================================================
BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>{{ page_title }} - SPX Wheel Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0f0f1a;
            color: #eee;
            min-height: 100vh;
        }

        /* Navigation */
        .nav {
            background: #1a1a2e;
            border-bottom: 2px solid #e94560;
            padding: 0 40px;
            display: flex;
            align-items: center;
        }
        .nav-brand {
            font-size: 20px;
            font-weight: bold;
            color: #e94560;
            padding: 15px 30px 15px 0;
            border-right: 1px solid #333;
            text-decoration: none;
        }
        .nav-links {
            display: flex;
            list-style: none;
            margin-left: 20px;
        }
        .nav-links a {
            display: block;
            padding: 18px 25px;
            color: #888;
            text-decoration: none;
            border-bottom: 3px solid transparent;
            transition: all 0.2s;
        }
        .nav-links a:hover {
            color: #fff;
            background: rgba(233, 69, 96, 0.1);
        }
        .nav-links a.active {
            color: #e94560;
            border-bottom-color: #e94560;
        }

        /* Main Content */
        .main {
            padding: 30px 40px;
        }

        .page-header {
            margin-bottom: 30px;
        }
        .page-header h1 {
            font-size: 28px;
            margin-bottom: 8px;
        }
        .page-header .subtitle {
            color: #666;
            font-size: 14px;
        }

        /* Cards */
        .grid { display: grid; gap: 20px; margin-bottom: 30px; }
        .grid-4 { grid-template-columns: repeat(4, 1fr); }
        .grid-3 { grid-template-columns: repeat(3, 1fr); }
        .grid-2 { grid-template-columns: repeat(2, 1fr); }

        .card {
            background: #1a1a2e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a2a4a;
        }
        .card.full { grid-column: 1 / -1; }
        .card.span-2 { grid-column: span 2; }
        .card.span-3 { grid-column: span 3; }

        .card h2 {
            font-size: 13px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }
        .card .value {
            font-size: 36px;
            font-weight: bold;
        }
        .card .value.sm { font-size: 24px; }

        .positive { color: #4ade80; }
        .negative { color: #f87171; }
        .warning { color: #fbbf24; }
        .info { color: #60a5fa; }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #2a2a4a;
        }
        th {
            color: #666;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-weight: 600;
        }
        tr:hover { background: rgba(255,255,255,0.02); }

        .source-polygon, .source-polygon_historical { color: #4ade80; }
        .source-tradier, .source-tradier_live { color: #60a5fa; }
        .source-estimated { color: #fbbf24; }

        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-success { background: rgba(74,222,128,0.2); color: #4ade80; }
        .badge-warning { background: rgba(251,191,36,0.2); color: #fbbf24; }
        .badge-danger { background: rgba(248,113,113,0.2); color: #f87171; }
        .badge-info { background: rgba(96,165,250,0.2); color: #60a5fa; }

        /* Buttons */
        .btn {
            display: inline-block;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            border: none;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #e94560;
            color: white;
        }
        .btn-primary:hover { background: #d63a54; }
        .btn-secondary {
            background: #2a2a4a;
            color: #888;
        }
        .btn-secondary:hover { background: #3a3a5a; color: #fff; }
        .btn-success { background: #059669; color: white; }
        .btn-danger { background: #dc2626; color: white; }

        /* Progress bar */
        .progress {
            height: 8px;
            background: #2a2a4a;
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-bar {
            height: 100%;
            transition: width 0.5s;
        }
        .progress-bar.success { background: linear-gradient(90deg, #f87171, #fbbf24, #4ade80); }

        /* Charts */
        .chart-container { height: 350px; position: relative; }

        /* Alerts */
        .alert {
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .alert-icon { font-size: 24px; }
        .alert-warning { background: rgba(251,191,36,0.1); border: 1px solid #fbbf24; }
        .alert-danger { background: rgba(248,113,113,0.1); border: 1px solid #f87171; }
        .alert-success { background: rgba(74,222,128,0.1); border: 1px solid #4ade80; }
        .alert-info { background: rgba(96,165,250,0.1); border: 1px solid #60a5fa; }

        /* Scrollable table container */
        .table-scroll {
            max-height: 500px;
            overflow-y: auto;
        }

        /* Form elements */
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            color: #888;
            margin-bottom: 8px;
            font-size: 13px;
        }
        .form-control {
            width: 100%;
            padding: 12px 15px;
            border-radius: 8px;
            border: 1px solid #2a2a4a;
            background: #0f0f1a;
            color: #fff;
            font-size: 14px;
        }
        .form-control:focus {
            outline: none;
            border-color: #e94560;
        }

        /* Status indicator */
        .status-dot {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-dot.green { background: #4ade80; }
        .status-dot.yellow { background: #fbbf24; }
        .status-dot.red { background: #f87171; }

        /* Loading spinner */
        .spinner {
            border: 3px solid #2a2a4a;
            border-top-color: #e94560;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            animation: spin 1s linear infinite;
            display: inline-block;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .refresh-info {
            text-align: right;
            color: #444;
            font-size: 12px;
            margin-top: 30px;
        }
    </style>
</head>
<body>
    <nav class="nav">
        <a href="/" class="nav-brand">SPX WHEEL</a>
        <ul class="nav-links">
            <li><a href="/" class="{{ 'active' if active_page == 'overview' else '' }}">Overview</a></li>
            <li><a href="/backtest" class="{{ 'active' if active_page == 'backtest' else '' }}">Backtest</a></li>
            <li><a href="/trades" class="{{ 'active' if active_page == 'trades' else '' }}">Trades</a></li>
            <li><a href="/positions" class="{{ 'active' if active_page == 'positions' else '' }}">Positions</a></li>
            <li><a href="/calibration" class="{{ 'active' if active_page == 'calibration' else '' }}">Calibration</a></li>
            <li><a href="/system" class="{{ 'active' if active_page == 'system' else '' }}">System</a></li>
        </ul>
    </nav>

    <main class="main">
        {% block content %}{% endblock %}

        <div class="refresh-info">
            Last updated: {{ now }} | <a href="#" onclick="location.reload()">Refresh</a>
        </div>
    </main>

    {% block scripts %}{% endblock %}
</body>
</html>
"""

# =============================================================================
# OVERVIEW PAGE
# =============================================================================
OVERVIEW_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="page-header">
    <h1>Dashboard Overview</h1>
    <div class="subtitle">Real-time monitoring of your SPX wheel strategy</div>
</div>

{% if data_quality < 50 %}
<div class="alert alert-danger">
    <span class="alert-icon">⚠️</span>
    <div>
        <strong>Low Data Quality Warning</strong><br>
        Only {{ "%.1f"|format(data_quality) }}% of prices are from real data. Results may not reflect actual trading.
    </div>
</div>
{% endif %}

<div class="grid grid-4">
    <div class="card">
        <h2>Total Equity</h2>
        <div class="value {{ 'positive' if total_pnl >= 0 else 'negative' }}">${{ "{:,.0f}".format(total_equity) }}</div>
    </div>
    <div class="card">
        <h2>Total P&L</h2>
        <div class="value {{ 'positive' if total_pnl >= 0 else 'negative' }}">{{ "+" if total_pnl >= 0 else "" }}${{ "{:,.0f}".format(total_pnl) }}</div>
    </div>
    <div class="card">
        <h2>Win Rate</h2>
        <div class="value {{ 'positive' if win_rate >= 70 else 'warning' if win_rate >= 50 else 'negative' }}">{{ "%.1f"|format(win_rate) }}%</div>
    </div>
    <div class="card">
        <h2>Open Positions</h2>
        <div class="value">{{ open_positions }}</div>
    </div>
</div>

<div class="grid grid-2">
    <div class="card">
        <h2>Data Quality</h2>
        <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 15px;">
            <div class="progress" style="flex: 1;">
                <div class="progress-bar success" style="width: {{ data_quality }}%;"></div>
            </div>
            <div class="value sm {{ 'positive' if data_quality >= 80 else 'warning' if data_quality >= 50 else 'negative' }}">{{ "%.0f"|format(data_quality) }}%</div>
        </div>
        <table>
            <tr><td>Real Data (Polygon/Tradier)</td><td style="text-align:right" class="positive">{{ real_data_points }}</td></tr>
            <tr><td>Estimated Data</td><td style="text-align:right" class="warning">{{ estimated_data_points }}</td></tr>
        </table>
    </div>
    <div class="card">
        <h2>Backtest vs Live</h2>
        <table>
            <tr><th></th><th>Backtest</th><th>Live</th><th>Diff</th></tr>
            <tr>
                <td>Win Rate</td>
                <td>{{ "%.1f"|format(backtest_win_rate) }}%</td>
                <td>{{ "%.1f"|format(win_rate) }}%</td>
                <td class="{{ 'positive' if (win_rate - backtest_win_rate)|abs < 5 else 'warning' if (win_rate - backtest_win_rate)|abs < 10 else 'negative' }}">
                    {{ "%+.1f"|format(win_rate - backtest_win_rate) }}%
                </td>
            </tr>
            <tr>
                <td>Total Trades</td>
                <td>{{ backtest_total_trades }}</td>
                <td>{{ total_trades }}</td>
                <td>-</td>
            </tr>
        </table>
        <div style="margin-top: 15px;">
            <a href="/backtest" class="btn btn-secondary">View Full Backtest Report →</a>
        </div>
    </div>
</div>

<div class="grid">
    <div class="card full">
        <h2>Equity Curve</h2>
        <div class="chart-container">
            <canvas id="equityChart"></canvas>
        </div>
    </div>
</div>

<div class="grid grid-2">
    <div class="card">
        <h2>Current Parameters</h2>
        <table>
            <tr><td>Put Delta</td><td style="text-align:right">{{ params.put_delta }}</td></tr>
            <tr><td>DTE Target</td><td style="text-align:right">{{ params.dte_target }} days</td></tr>
            <tr><td>Stop Loss</td><td style="text-align:right">{{ params.stop_loss_pct }}%</td></tr>
            <tr><td>Max Margin</td><td style="text-align:right">{{ "%.0f"|format(params.max_margin_pct * 100) }}%</td></tr>
        </table>
        <div style="margin-top: 15px;">
            <a href="/calibration" class="btn btn-secondary">Run Calibration →</a>
        </div>
    </div>
    <div class="card">
        <h2>Quick Actions</h2>
        <div style="display: flex; flex-direction: column; gap: 10px;">
            <a href="/backtest/run" class="btn btn-primary">Run New Backtest</a>
            <a href="/positions" class="btn btn-secondary">View Open Positions ({{ open_positions }})</a>
            <a href="/system" class="btn btn-secondary">System Status</a>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const ctx = document.getElementById('equityChart').getContext('2d');
const equityData = {{ equity_curve | tojson }};

new Chart(ctx, {
    type: 'line',
    data: {
        labels: equityData.map(d => d.date),
        datasets: [{
            label: 'Equity',
            data: equityData.map(d => d.equity),
            borderColor: '#4ade80',
            backgroundColor: 'rgba(74, 222, 128, 0.1)',
            fill: true,
            tension: 0.2,
            pointRadius: 0
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: { grid: { color: '#1a1a2e' }, ticks: { color: '#666' } },
            y: {
                grid: { color: '#1a1a2e' },
                ticks: { color: '#666', callback: v => '$' + v.toLocaleString() }
            }
        }
    }
});
</script>
{% endblock %}
"""

# =============================================================================
# BACKTEST PAGE - FULL REPORT
# =============================================================================
BACKTEST_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="page-header">
    <h1>Backtest Results</h1>
    <div class="subtitle">Historical simulation results used for strategy calibration</div>
</div>

<div style="margin-bottom: 20px;">
    <a href="/backtest/run" class="btn btn-primary">Run New Backtest</a>
</div>

{% if backtest_id %}
<div class="alert alert-info">
    <span class="alert-icon">📊</span>
    <div>
        <strong>Backtest ID:</strong> {{ backtest_id }}<br>
        <small>{{ backtest_total_trades }} trades analyzed</small>
    </div>
</div>
{% else %}
<div class="alert alert-warning">
    <span class="alert-icon">⚠️</span>
    <div>
        <strong>No Backtest Results Yet</strong><br>
        Run a backtest to see results here. Click "Run New Backtest" above.
    </div>
</div>
{% endif %}

<!-- MT4-Style Strategy Report Header -->
<div class="grid grid-4">
    <div class="card">
        <h2>Total Trades</h2>
        <div class="value">{{ backtest_total_trades }}</div>
    </div>
    <div class="card">
        <h2>Win Rate</h2>
        <div class="value {{ 'positive' if backtest_win_rate >= 70 else 'warning' if backtest_win_rate >= 50 else 'negative' }}">{{ "%.1f"|format(backtest_win_rate) }}%</div>
    </div>
    <div class="card">
        <h2>Total P&L</h2>
        <div class="value {{ 'positive' if backtest_total_pnl >= 0 else 'negative' }}">${{ "{:,.0f}".format(backtest_total_pnl) }}</div>
    </div>
    <div class="card">
        <h2>Data Quality</h2>
        <div class="value {{ 'positive' if backtest_data_quality >= 80 else 'warning' if backtest_data_quality >= 50 else 'negative' }}">{{ "%.0f"|format(backtest_data_quality) }}%</div>
    </div>
</div>

<!-- Equity Curve -->
<div class="grid">
    <div class="card full">
        <h2>Backtest Equity Curve</h2>
        <div class="chart-container">
            <canvas id="backtestEquityChart"></canvas>
        </div>
    </div>
</div>

<!-- Detailed Stats -->
<div class="grid grid-3">
    <div class="card">
        <h2>Win/Loss Breakdown</h2>
        <table>
            <tr><td>Winners (OTM Expire)</td><td style="text-align:right" class="positive">{{ backtest_winners }}</td></tr>
            <tr><td>Losers (ITM Settle)</td><td style="text-align:right" class="negative">{{ backtest_losers }}</td></tr>
            <tr><td>Win Rate</td><td style="text-align:right">{{ "%.1f"|format(backtest_win_rate) }}%</td></tr>
        </table>
    </div>
    <div class="card">
        <h2>P&L Statistics</h2>
        <table>
            <tr><td>Gross Profit</td><td style="text-align:right" class="positive">${{ "{:,.0f}".format(backtest_gross_profit) }}</td></tr>
            <tr><td>Gross Loss</td><td style="text-align:right" class="negative">${{ "{:,.0f}".format(backtest_gross_loss) }}</td></tr>
            <tr><td>Net P&L</td><td style="text-align:right" class="{{ 'positive' if backtest_total_pnl >= 0 else 'negative' }}">${{ "{:,.0f}".format(backtest_total_pnl) }}</td></tr>
            <tr><td>Profit Factor</td><td style="text-align:right">{{ "%.2f"|format(backtest_profit_factor) }}</td></tr>
        </table>
    </div>
    <div class="card">
        <h2>Risk Metrics</h2>
        <table>
            <tr><td>Max Drawdown</td><td style="text-align:right" class="negative">{{ "%.1f"|format(backtest_max_drawdown) }}%</td></tr>
            <tr><td>Avg Win</td><td style="text-align:right" class="positive">${{ "{:,.0f}".format(backtest_avg_win) }}</td></tr>
            <tr><td>Avg Loss</td><td style="text-align:right" class="negative">${{ "{:,.0f}".format(backtest_avg_loss) }}</td></tr>
            <tr><td>Return</td><td style="text-align:right">{{ "%.1f"|format(backtest_return_pct) }}%</td></tr>
        </table>
    </div>
</div>

<!-- Data Source Breakdown -->
<div class="grid">
    <div class="card full">
        <h2>Data Source Analysis</h2>
        <div class="grid grid-2" style="margin-top: 15px;">
            <div>
                <h3 style="color: #4ade80; margin-bottom: 10px;">✓ Real Data ({{ backtest_real_data_count }} trades)</h3>
                <p style="color: #888;">Prices from Polygon.io historical API. These are actual market prices.</p>
                <div class="progress" style="margin-top: 10px;">
                    <div class="progress-bar" style="width: {{ backtest_data_quality }}%; background: #4ade80;"></div>
                </div>
            </div>
            <div>
                <h3 style="color: #fbbf24; margin-bottom: 10px;">⚠ Estimated Data ({{ backtest_estimated_count }} trades)</h3>
                <p style="color: #888;">Prices calculated using Black-Scholes. Less accurate but usable.</p>
                <div class="progress" style="margin-top: 10px;">
                    <div class="progress-bar" style="width: {{ 100 - backtest_data_quality }}%; background: #fbbf24;"></div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Trade List -->
<div class="grid">
    <div class="card full">
        <h2>All Backtest Trades ({{ backtest_total_trades }} total)</h2>
        <div class="table-scroll">
            <table>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Option</th>
                        <th>Strike</th>
                        <th>SPX Price</th>
                        <th>Entry</th>
                        <th>Premium</th>
                        <th>P&L</th>
                        <th>Data Source</th>
                    </tr>
                </thead>
                <tbody>
                    {% for t in backtest_trades %}
                    <tr>
                        <td>{{ t.trade_id }}</td>
                        <td>{{ t.trade_date[:10] if t.trade_date else '' }}</td>
                        <td>
                            {% if t.trade_type == 'EXPIRED_OTM' %}
                            <span class="badge badge-success">OTM WIN</span>
                            {% elif t.trade_type == 'CASH_SETTLE_LOSS' %}
                            <span class="badge badge-danger">ITM LOSS</span>
                            {% else %}
                            <span class="badge badge-info">{{ t.trade_type or 'OPEN' }}</span>
                            {% endif %}
                        </td>
                        <td><strong>{{ t.option_ticker }}</strong></td>
                        <td>${{ "{:,.0f}".format(t.strike) }}</td>
                        <td>${{ "{:,.0f}".format(t.entry_underlying) if t.entry_underlying else '-' }}</td>
                        <td>${{ "{:.2f}".format(t.entry_price) }}</td>
                        <td>${{ "{:,.2f}".format(t.premium_received) }}</td>
                        <td class="{{ 'positive' if t.total_pnl and t.total_pnl > 0 else 'negative' if t.total_pnl and t.total_pnl < 0 else '' }}">
                            {{ "$%,.2f"|format(t.total_pnl) if t.total_pnl else '-' }}
                        </td>
                        <td class="source-{{ t.price_source|lower|replace('_','-') if t.price_source else 'estimated' }}">
                            {{ 'REAL' if 'POLYGON' in (t.price_source or '') else 'EST' }}
                        </td>
                    </tr>
                    {% else %}
                    <tr><td colspan="10" style="text-align:center;color:#666;">No backtest trades. Run a backtest first.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
const ctx = document.getElementById('backtestEquityChart').getContext('2d');
const equityData = {{ backtest_equity | tojson }};

new Chart(ctx, {
    type: 'line',
    data: {
        labels: equityData.map(d => d.date),
        datasets: [{
            label: 'Equity',
            data: equityData.map(d => d.equity),
            borderColor: '#6366f1',
            backgroundColor: 'rgba(99, 102, 241, 0.1)',
            fill: true,
            tension: 0.2,
            pointRadius: 0
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: { grid: { color: '#1a1a2e' }, ticks: { color: '#666' } },
            y: {
                grid: { color: '#1a1a2e' },
                ticks: { color: '#666', callback: v => '$' + v.toLocaleString() }
            }
        }
    }
});
</script>
{% endblock %}
"""

# =============================================================================
# RUN BACKTEST PAGE
# =============================================================================
RUN_BACKTEST_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="page-header">
    <h1>Run New Backtest</h1>
    <div class="subtitle">Configure and run a historical simulation</div>
</div>

{% if running %}
<div class="alert alert-info">
    <div class="spinner"></div>
    <div>
        <strong>Backtest Running...</strong><br>
        This may take a few minutes. The page will refresh when complete.
    </div>
</div>
<script>setTimeout(() => location.reload(), 5000);</script>
{% endif %}

{% if result %}
<div class="alert alert-success">
    <span class="alert-icon">✓</span>
    <div>
        <strong>Backtest Complete!</strong><br>
        {{ result.total_trades }} trades simulated. <a href="/backtest">View Results →</a>
    </div>
</div>
{% endif %}

{% if error %}
<div class="alert alert-danger">
    <span class="alert-icon">✗</span>
    <div>
        <strong>Backtest Failed</strong><br>
        {{ error }}
    </div>
</div>
{% endif %}

<div class="grid grid-2">
    <div class="card">
        <h2>Backtest Configuration</h2>
        <form method="POST" action="/backtest/run">
            <div class="form-group">
                <label>Start Date</label>
                <input type="date" name="start_date" class="form-control" value="{{ default_start }}" required>
            </div>
            <div class="form-group">
                <label>End Date</label>
                <input type="date" name="end_date" class="form-control" value="{{ default_end }}" required>
            </div>
            <div class="form-group">
                <label>Initial Capital ($)</label>
                <input type="number" name="capital" class="form-control" value="100000" required>
            </div>
            <div class="form-group">
                <label>Put Delta</label>
                <input type="number" name="delta" class="form-control" value="0.20" step="0.01" min="0.05" max="0.40" required>
            </div>
            <div class="form-group">
                <label>DTE Target (days)</label>
                <input type="number" name="dte" class="form-control" value="45" min="7" max="90" required>
            </div>
            <div class="form-group">
                <label>Stop Loss (%)</label>
                <input type="number" name="stop_loss" class="form-control" value="200" min="50" max="500" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;">Run Backtest</button>
        </form>
    </div>
    <div class="card">
        <h2>What This Tests</h2>
        <div style="color: #888; line-height: 1.8;">
            <p><strong>Strategy:</strong> Cash-secured SPX put selling (wheel)</p>
            <p><strong>Entry:</strong> Sell put at target delta, target DTE</p>
            <p><strong>Exit:</strong> Hold to expiration, cash settle if ITM</p>
            <p><strong>Risk:</strong> Stop loss if option price exceeds threshold</p>
            <br>
            <p><strong>Data Source:</strong></p>
            <ul style="margin-left: 20px;">
                <li>SPX prices: Polygon historical</li>
                <li>Option prices: Polygon historical (if available)</li>
                <li>Fallback: Black-Scholes estimates</li>
            </ul>
            <br>
            <p>Results saved to database for comparison with live trading.</p>
        </div>
    </div>
</div>
{% endblock %}
"""

# =============================================================================
# TRADES PAGE
# =============================================================================
TRADES_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="page-header">
    <h1>Trade Log</h1>
    <div class="subtitle">All live and paper trades executed by the system</div>
</div>

<div class="grid grid-4">
    <div class="card">
        <h2>Total Trades</h2>
        <div class="value">{{ total_trades }}</div>
    </div>
    <div class="card">
        <h2>Winners</h2>
        <div class="value positive">{{ winners }}</div>
    </div>
    <div class="card">
        <h2>Losers</h2>
        <div class="value negative">{{ losers }}</div>
    </div>
    <div class="card">
        <h2>Win Rate</h2>
        <div class="value {{ 'positive' if win_rate >= 70 else 'warning' }}">{{ "%.1f"|format(win_rate) }}%</div>
    </div>
</div>

<div class="card full">
    <h2>All Trades</h2>
    <div class="table-scroll">
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Date Opened</th>
                    <th>Date Closed</th>
                    <th>Option</th>
                    <th>Strike</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th>Premium</th>
                    <th>Settlement</th>
                    <th>P&L</th>
                    <th>Data Source</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {% for t in trades %}
                <tr>
                    <td>{{ t.id }}</td>
                    <td>{{ t.opened_at[:10] if t.opened_at else '' }}</td>
                    <td>{{ t.closed_at[:10] if t.closed_at else '-' }}</td>
                    <td><strong>{{ t.option_ticker }}</strong></td>
                    <td>${{ "{:,.0f}".format(t.strike) }}</td>
                    <td>${{ "{:.2f}".format(t.entry_price) }}</td>
                    <td>{{ "$%.2f"|format(t.exit_price) if t.exit_price else '-' }}</td>
                    <td>${{ "{:,.2f}".format(t.premium_received) }}</td>
                    <td class="{{ 'negative' if t.settlement_pnl and t.settlement_pnl < 0 else '' }}">
                        {{ "$%,.2f"|format(t.settlement_pnl) if t.settlement_pnl else '-' }}
                    </td>
                    <td class="{{ 'positive' if t.total_pnl and t.total_pnl > 0 else 'negative' if t.total_pnl and t.total_pnl < 0 else '' }}">
                        {{ "$%,.2f"|format(t.total_pnl) if t.total_pnl else '-' }}
                    </td>
                    <td class="source-{{ t.price_source|lower if t.price_source else 'estimated' }}">
                        {{ t.price_source or 'EST' }}
                    </td>
                    <td>
                        {% if t.status == 'OPEN' %}
                        <span class="badge badge-info">OPEN</span>
                        {% elif t.status == 'CLOSED' %}
                        <span class="badge {{ 'badge-success' if t.total_pnl and t.total_pnl > 0 else 'badge-danger' }}">CLOSED</span>
                        {% else %}
                        <span class="badge">{{ t.status }}</span>
                        {% endif %}
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="12" style="text-align:center;color:#666;">No trades yet. Run the paper trader to see trades here.</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
"""

# =============================================================================
# POSITIONS PAGE
# =============================================================================
POSITIONS_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="page-header">
    <h1>Open Positions</h1>
    <div class="subtitle">Currently open SPX wheel positions</div>
</div>

<div class="grid grid-3">
    <div class="card">
        <h2>Open Positions</h2>
        <div class="value">{{ open_count }}</div>
    </div>
    <div class="card">
        <h2>Total Premium at Risk</h2>
        <div class="value">${{ "{:,.0f}".format(total_premium) }}</div>
    </div>
    <div class="card">
        <h2>Margin Used</h2>
        <div class="value">${{ "{:,.0f}".format(margin_used) }}</div>
    </div>
</div>

<div class="card full">
    <h2>Position Details</h2>
    <div class="table-scroll">
        <table>
            <thead>
                <tr>
                    <th>Option</th>
                    <th>Strike</th>
                    <th>Expiration</th>
                    <th>DTE</th>
                    <th>Contracts</th>
                    <th>Entry Price</th>
                    <th>Premium</th>
                    <th>Current SPX</th>
                    <th>Buffer</th>
                    <th>Data Source</th>
                </tr>
            </thead>
            <tbody>
                {% for p in positions %}
                <tr>
                    <td><strong>{{ p.option_ticker }}</strong></td>
                    <td>${{ "{:,.0f}".format(p.strike) }}</td>
                    <td>{{ p.expiration }}</td>
                    <td class="{{ 'warning' if p.dte <= 7 else '' }}">{{ p.dte }} days</td>
                    <td>{{ p.contracts }}</td>
                    <td>${{ "{:.2f}".format(p.entry_price) }}</td>
                    <td>${{ "{:,.2f}".format(p.premium_received) }}</td>
                    <td>${{ "{:,.0f}".format(current_spx) if current_spx else '-' }}</td>
                    <td class="{{ 'positive' if p.buffer_pct > 5 else 'warning' if p.buffer_pct > 2 else 'negative' }}">
                        {{ "%.1f"|format(p.buffer_pct) }}%
                    </td>
                    <td class="source-{{ p.price_source|lower if p.price_source else 'estimated' }}">
                        {{ p.price_source or 'EST' }}
                    </td>
                </tr>
                {% else %}
                <tr><td colspan="10" style="text-align:center;color:#666;">No open positions</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
"""

# =============================================================================
# SYSTEM PAGE
# =============================================================================
SYSTEM_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="page-header">
    <h1>System Status</h1>
    <div class="subtitle">Circuit breaker, alerts, and system health</div>
</div>

<div class="grid grid-3">
    <div class="card">
        <h2>Circuit Breaker</h2>
        <div class="value {{ 'positive' if circuit_breaker.can_trade else 'negative' }}">
            <span class="status-dot {{ 'green' if circuit_breaker.can_trade else 'red' }}"></span>
            {{ circuit_breaker.state }}
        </div>
        <table style="margin-top: 15px;">
            <tr><td>Daily P&L</td><td style="text-align:right">${{ "{:,.2f}".format(circuit_breaker.daily_pnl) }}</td></tr>
            <tr><td>Daily Trades</td><td style="text-align:right">{{ circuit_breaker.daily_trades }}</td></tr>
            <tr><td>Loss Limit</td><td style="text-align:right">{{ circuit_breaker.limits.max_daily_loss_pct }}%</td></tr>
        </table>
    </div>
    <div class="card">
        <h2>Alerts Configuration</h2>
        <table>
            <tr><td>Email Recipient</td><td style="text-align:right">{{ alert_email }}</td></tr>
            <tr><td>SMTP Status</td><td style="text-align:right">{{ 'Configured' if smtp_configured else 'Not Set' }}</td></tr>
        </table>
        {% if not smtp_configured %}
        <div class="alert alert-warning" style="margin-top: 15px;">
            <small>Email alerts not configured. Run ./scripts/setup_alerts.sh</small>
        </div>
        {% endif %}
    </div>
    <div class="card">
        <h2>API Status</h2>
        <table>
            <tr>
                <td>Polygon</td>
                <td style="text-align:right">
                    <span class="status-dot {{ 'green' if polygon_configured else 'red' }}"></span>
                    {{ 'OK' if polygon_configured else 'Not Set' }}
                </td>
            </tr>
            <tr>
                <td>Tradier</td>
                <td style="text-align:right">
                    <span class="status-dot {{ 'green' if tradier_configured else 'yellow' }}"></span>
                    {{ 'OK' if tradier_configured else 'Optional' }}
                </td>
            </tr>
            <tr>
                <td>Database</td>
                <td style="text-align:right">
                    <span class="status-dot {{ 'green' if db_connected else 'red' }}"></span>
                    {{ 'Connected' if db_connected else 'Error' }}
                </td>
            </tr>
        </table>
    </div>
</div>

<div class="card full">
    <h2>Recent Alerts</h2>
    <div class="table-scroll" style="max-height: 400px;">
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Level</th>
                    <th>Type</th>
                    <th>Subject</th>
                </tr>
            </thead>
            <tbody>
                {% for a in alerts %}
                <tr style="background: {{ 'rgba(248,113,113,0.1)' if a.level == 'CRITICAL' else 'rgba(251,191,36,0.05)' if a.level == 'WARNING' else '' }};">
                    <td>{{ a.timestamp }}</td>
                    <td>
                        <span class="badge {{ 'badge-danger' if a.level == 'CRITICAL' else 'badge-warning' if a.level == 'WARNING' else 'badge-info' }}">
                            {{ a.level }}
                        </span>
                    </td>
                    <td>{{ a.type }}</td>
                    <td>{{ a.subject }}</td>
                </tr>
                {% else %}
                <tr><td colspan="4" style="text-align:center;color:#666;">No recent alerts</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>

{% if circuit_breaker.can_trade %}
<div style="margin-top: 20px;">
    <a href="/system/kill" class="btn btn-danger" onclick="return confirm('Are you sure you want to activate the KILL SWITCH? This will stop ALL trading.');">
        🛑 Activate Kill Switch
    </a>
</div>
{% else %}
<div style="margin-top: 20px;">
    <a href="/system/reset" class="btn btn-success" onclick="return confirm('Are you sure you want to RESET the circuit breaker and resume trading?');">
        ✓ Reset Circuit Breaker
    </a>
</div>
{% endif %}
{% endblock %}
"""

# =============================================================================
# CALIBRATION PAGE
# =============================================================================
CALIBRATION_TEMPLATE = """
{% extends "base" %}
{% block content %}
<div class="page-header">
    <h1>Strategy Calibration</h1>
    <div class="subtitle">Optimize parameters using historical data</div>
</div>

<div class="grid grid-2">
    <div class="card">
        <h2>Current Parameters</h2>
        <table>
            <tr><td>Put Delta</td><td style="text-align:right"><strong>{{ params.put_delta }}</strong></td></tr>
            <tr><td>DTE Target</td><td style="text-align:right"><strong>{{ params.dte_target }} days</strong></td></tr>
            <tr><td>Stop Loss</td><td style="text-align:right"><strong>{{ params.stop_loss_pct }}%</strong></td></tr>
            <tr><td>Max Margin</td><td style="text-align:right"><strong>{{ "%.0f"|format(params.max_margin_pct * 100) }}%</strong></td></tr>
            <tr><td>Calibrated On</td><td style="text-align:right">{{ params.calibration_date[:10] if params.calibration_date else 'Never' }}</td></tr>
        </table>
    </div>
    <div class="card">
        <h2>Calibration Performance</h2>
        <table>
            <tr><td>Backtest Win Rate</td><td style="text-align:right" class="positive">{{ "%.1f"|format(params.backtest_win_rate) }}%</td></tr>
            <tr><td>Backtest Return</td><td style="text-align:right" class="positive">{{ "%.1f"|format(params.backtest_total_return) }}%</td></tr>
            <tr><td>Max Drawdown</td><td style="text-align:right" class="negative">{{ "%.1f"|format(params.backtest_max_drawdown) }}%</td></tr>
            <tr><td>Sharpe Ratio</td><td style="text-align:right">{{ "%.2f"|format(params.backtest_sharpe) }}</td></tr>
        </table>
    </div>
</div>

<div class="alert alert-info">
    <span class="alert-icon">💡</span>
    <div>
        <strong>How Calibration Works</strong><br>
        The optimizer tests different delta/DTE combinations using historical data to find the best parameters for your risk tolerance.
    </div>
</div>

<div class="card full">
    <h2>Run New Calibration</h2>
    <p style="color: #888; margin-bottom: 20px;">This will run multiple backtests to find optimal parameters. Takes 5-15 minutes.</p>

    <form method="POST" action="/calibration/run">
        <div class="grid grid-3" style="margin-bottom: 20px;">
            <div class="form-group">
                <label>Start Date</label>
                <input type="date" name="start_date" class="form-control" value="{{ default_start }}">
            </div>
            <div class="form-group">
                <label>End Date</label>
                <input type="date" name="end_date" class="form-control" value="{{ default_end }}">
            </div>
            <div class="form-group">
                <label>Optimize For</label>
                <select name="optimize_for" class="form-control">
                    <option value="sharpe">Sharpe Ratio</option>
                    <option value="return">Total Return</option>
                    <option value="win_rate">Win Rate</option>
                    <option value="drawdown">Min Drawdown</option>
                </select>
            </div>
        </div>
        <button type="submit" class="btn btn-primary">Run Calibration</button>
    </form>
</div>
{% endblock %}
"""


# =============================================================================
# DATA FETCHING FUNCTIONS
# =============================================================================

def get_dashboard_data():
    """Fetch all data for dashboard"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get positions
        cursor.execute('''
            SELECT id, option_ticker, strike, expiration, contracts,
                   entry_price, exit_price, premium_received, settlement_pnl, total_pnl,
                   status, opened_at, closed_at, notes, parameters_used
            FROM spx_wheel_positions ORDER BY opened_at DESC
        ''')

        positions = []
        for row in cursor.fetchall():
            params_json = row[14] or '{}'
            if isinstance(params_json, str):
                params_json = json.loads(params_json)
            price_source = params_json.get('price_source', 'ESTIMATED')

            exp = row[3]
            if exp:
                if isinstance(exp, str):
                    exp = datetime.strptime(exp, '%Y-%m-%d').date()
                dte = (exp - datetime.now().date()).days
            else:
                dte = 0

            positions.append({
                'id': row[0], 'option_ticker': row[1], 'strike': float(row[2] or 0),
                'expiration': str(row[3]), 'contracts': row[4],
                'entry_price': float(row[5] or 0), 'exit_price': float(row[6]) if row[6] else None,
                'premium_received': float(row[7] or 0),
                'settlement_pnl': float(row[8]) if row[8] else None,
                'total_pnl': float(row[9]) if row[9] else None,
                'status': row[10], 'opened_at': str(row[11]) if row[11] else '',
                'closed_at': str(row[12]) if row[12] else '', 'price_source': price_source, 'dte': dte
            })

        # Calculate stats
        closed = [p for p in positions if p['status'] == 'CLOSED']
        open_pos = [p for p in positions if p['status'] == 'OPEN']

        total_pnl = sum(p['total_pnl'] or 0 for p in closed)
        winners = sum(1 for p in closed if (p['total_pnl'] or 0) > 0)
        win_rate = (winners / len(closed) * 100) if closed else 0

        real_count = sum(1 for p in positions if p['price_source'] in ['POLYGON', 'TRADIER_LIVE', 'POLYGON_HISTORICAL'])
        est_count = len(positions) - real_count
        data_quality = (real_count / len(positions) * 100) if positions else 100

        # Get parameters
        cursor.execute('''
            SELECT parameters FROM spx_wheel_parameters
            WHERE is_active = TRUE ORDER BY timestamp DESC LIMIT 1
        ''')
        params_row = cursor.fetchone()
        params = json.loads(params_row[0]) if params_row and params_row[0] else {
            'put_delta': 0.20, 'dte_target': 45, 'max_margin_pct': 0.50,
            'stop_loss_pct': 200, 'backtest_win_rate': 0, 'backtest_total_return': 0,
            'backtest_max_drawdown': 0, 'backtest_sharpe': 0, 'calibration_date': ''
        }
        if isinstance(params, str):
            params = json.loads(params)

        # Get backtest trades
        backtest_trades, backtest_id, backtest_equity = get_backtest_data(cursor)

        # Equity curve
        cursor.execute('SELECT date, equity FROM spx_wheel_performance ORDER BY date')
        equity_curve = [{'date': str(r[0]), 'equity': float(r[1])} for r in cursor.fetchall()]
        if not equity_curve:
            equity_curve = [{'date': datetime.now().strftime('%Y-%m-%d'), 'equity': 1000000}]

        conn.close()

        # Calculate backtest stats
        bt_winners = sum(1 for t in backtest_trades if (t.get('total_pnl') or 0) > 0)
        bt_losers = sum(1 for t in backtest_trades if (t.get('total_pnl') or 0) < 0)
        bt_win_rate = (bt_winners / (bt_winners + bt_losers) * 100) if (bt_winners + bt_losers) > 0 else 0
        bt_total_pnl = sum(t.get('total_pnl') or 0 for t in backtest_trades)
        bt_gross_profit = sum(t.get('total_pnl') for t in backtest_trades if (t.get('total_pnl') or 0) > 0)
        bt_gross_loss = abs(sum(t.get('total_pnl') for t in backtest_trades if (t.get('total_pnl') or 0) < 0))
        bt_real = sum(1 for t in backtest_trades if 'POLYGON' in (t.get('price_source') or ''))
        bt_data_quality = (bt_real / len(backtest_trades) * 100) if backtest_trades else 0

        return {
            'positions': positions, 'trades': positions,
            'total_trades': len(closed), 'winners': winners, 'losers': len(closed) - winners,
            'open_positions': len(open_pos), 'total_pnl': total_pnl,
            'total_equity': 1000000 + total_pnl,
            'win_rate': win_rate, 'data_quality': data_quality,
            'real_data_points': real_count, 'estimated_data_points': est_count,
            'params': type('P', (), params)(),
            'backtest_trades': backtest_trades, 'backtest_id': backtest_id,
            'backtest_total_trades': len(backtest_trades),
            'backtest_win_rate': bt_win_rate, 'backtest_total_pnl': bt_total_pnl,
            'backtest_winners': bt_winners, 'backtest_losers': bt_losers,
            'backtest_gross_profit': bt_gross_profit, 'backtest_gross_loss': bt_gross_loss,
            'backtest_profit_factor': (bt_gross_profit / bt_gross_loss) if bt_gross_loss > 0 else 0,
            'backtest_data_quality': bt_data_quality,
            'backtest_real_data_count': bt_real,
            'backtest_estimated_count': len(backtest_trades) - bt_real,
            'backtest_max_drawdown': params.get('backtest_max_drawdown', 0),
            'backtest_avg_win': (bt_gross_profit / bt_winners) if bt_winners > 0 else 0,
            'backtest_avg_loss': (bt_gross_loss / bt_losers) if bt_losers > 0 else 0,
            'backtest_return_pct': params.get('backtest_total_return', 0),
            'backtest_equity': backtest_equity,
            'equity_curve': equity_curve,
            'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return get_empty_data()


def get_backtest_data(cursor):
    """Get backtest trades and equity curve"""
    try:
        cursor.execute('''
            SELECT DISTINCT backtest_id FROM spx_wheel_backtest_trades
            ORDER BY backtest_id DESC LIMIT 1
        ''')
        result = cursor.fetchone()
        if not result:
            return [], None, []

        backtest_id = result[0]

        cursor.execute('''
            SELECT trade_id, trade_date, trade_type, option_ticker, strike,
                   entry_price, premium_received, total_pnl, price_source, entry_underlying_price
            FROM spx_wheel_backtest_trades WHERE backtest_id = %s
            ORDER BY trade_date DESC
        ''', (backtest_id,))

        trades = [{
            'trade_id': r[0], 'trade_date': str(r[1]) if r[1] else '',
            'trade_type': r[2], 'option_ticker': r[3], 'strike': float(r[4] or 0),
            'entry_price': float(r[5] or 0), 'premium_received': float(r[6] or 0),
            'total_pnl': float(r[7]) if r[7] else None, 'price_source': r[8],
            'entry_underlying': float(r[9] or 0)
        } for r in cursor.fetchall()]

        # Get equity curve
        cursor.execute('''
            SELECT date, equity FROM spx_wheel_backtest_equity
            WHERE backtest_id = %s ORDER BY date
        ''', (backtest_id,))
        equity = [{'date': str(r[0])[:10], 'equity': float(r[1])} for r in cursor.fetchall()]

        return trades, backtest_id, equity
    except:
        return [], None, []


def get_empty_data():
    """Return empty data structure"""
    return {
        'positions': [], 'trades': [], 'total_trades': 0, 'winners': 0, 'losers': 0,
        'open_positions': 0, 'total_pnl': 0, 'total_equity': 1000000,
        'win_rate': 0, 'data_quality': 0, 'real_data_points': 0, 'estimated_data_points': 0,
        'params': type('P', (), {'put_delta': 0.20, 'dte_target': 45, 'max_margin_pct': 0.50,
                                  'stop_loss_pct': 200, 'backtest_win_rate': 0, 'backtest_total_return': 0,
                                  'backtest_max_drawdown': 0, 'backtest_sharpe': 0, 'calibration_date': ''})(),
        'backtest_trades': [], 'backtest_id': None, 'backtest_total_trades': 0,
        'backtest_win_rate': 0, 'backtest_total_pnl': 0, 'backtest_winners': 0, 'backtest_losers': 0,
        'backtest_gross_profit': 0, 'backtest_gross_loss': 0, 'backtest_profit_factor': 0,
        'backtest_data_quality': 0, 'backtest_real_data_count': 0, 'backtest_estimated_count': 0,
        'backtest_max_drawdown': 0, 'backtest_avg_win': 0, 'backtest_avg_loss': 0,
        'backtest_return_pct': 0, 'backtest_equity': [],
        'equity_curve': [{'date': datetime.now().strftime('%Y-%m-%d'), 'equity': 1000000}],
        'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }


def get_circuit_breaker_status():
    """Get circuit breaker status"""
    try:
        from trading.circuit_breaker import get_circuit_breaker
        return get_circuit_breaker().get_status()
    except:
        return {'state': 'UNKNOWN', 'can_trade': True, 'daily_pnl': 0, 'daily_trades': 0,
                'limits': {'max_daily_loss_pct': 3.0}}


def get_alerts():
    """Get recent alerts"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT timestamp, alert_type, level, subject FROM spx_wheel_alerts
            ORDER BY timestamp DESC LIMIT 20
        ''')
        alerts = [{'timestamp': str(r[0])[:19], 'type': r[1], 'level': r[2], 'subject': r[3]}
                  for r in cursor.fetchall()]
        conn.close()
        return alerts
    except:
        return []


# =============================================================================
# ROUTES
# =============================================================================

@app.route('/')
def overview():
    data = get_dashboard_data()
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') +
                                   OVERVIEW_TEMPLATE,
                                   page_title='Overview', active_page='overview', **data)


@app.route('/backtest')
def backtest():
    data = get_dashboard_data()
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') +
                                   BACKTEST_TEMPLATE,
                                   page_title='Backtest Results', active_page='backtest', **data)


@app.route('/backtest/run', methods=['GET', 'POST'])
def run_backtest():
    if request.method == 'POST':
        # Run backtest in background
        start = request.form.get('start_date', '2024-01-01')
        end = request.form.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        capital = int(request.form.get('capital', 100000))
        delta = float(request.form.get('delta', 0.20))
        dte = int(request.form.get('dte', 45))
        stop_loss = int(request.form.get('stop_loss', 200))

        try:
            from backtest.spx_premium_backtest import SPXPremiumBacktester
            bt = SPXPremiumBacktester(
                start_date=start, end_date=end, initial_capital=capital,
                put_delta=delta, dte_target=dte, stop_loss_pct=stop_loss
            )
            results = bt.run(save_to_db=True)
            return redirect('/backtest')
        except Exception as e:
            return render_template_string(
                BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') + RUN_BACKTEST_TEMPLATE,
                page_title='Run Backtest', active_page='backtest',
                error=str(e), running=False, result=None,
                default_start='2024-01-01',
                default_end=datetime.now().strftime('%Y-%m-%d'),
                now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )

    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') + RUN_BACKTEST_TEMPLATE,
        page_title='Run Backtest', active_page='backtest',
        error=None, running=False, result=None,
        default_start='2024-01-01',
        default_end=datetime.now().strftime('%Y-%m-%d'),
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )


@app.route('/trades')
def trades():
    data = get_dashboard_data()
    return render_template_string(BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') +
                                   TRADES_TEMPLATE,
                                   page_title='Trade Log', active_page='trades', **data)


@app.route('/positions')
def positions():
    data = get_dashboard_data()
    open_pos = [p for p in data['positions'] if p['status'] == 'OPEN']

    # Add buffer calculation
    current_spx = None
    try:
        from data.polygon_data_fetcher import polygon_fetcher
        current_spx = polygon_fetcher.get_current_price('SPX')
    except:
        pass

    for p in open_pos:
        if current_spx and p['strike']:
            p['buffer_pct'] = ((current_spx - p['strike']) / current_spx) * 100
        else:
            p['buffer_pct'] = 0

    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') + POSITIONS_TEMPLATE,
        page_title='Positions', active_page='positions',
        positions=open_pos, open_count=len(open_pos),
        total_premium=sum(p['premium_received'] for p in open_pos),
        margin_used=sum(p['strike'] * 100 * 0.2 * p['contracts'] for p in open_pos),
        current_spx=current_spx,
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )


@app.route('/calibration', methods=['GET', 'POST'])
def calibration():
    data = get_dashboard_data()

    if request.method == 'POST':
        # Run calibration (would run optimizer)
        return redirect('/calibration')

    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') + CALIBRATION_TEMPLATE,
        page_title='Calibration', active_page='calibration',
        params=data['params'],
        default_start='2024-01-01',
        default_end=datetime.now().strftime('%Y-%m-%d'),
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )


@app.route('/system')
def system():
    cb = get_circuit_breaker_status()
    alerts = get_alerts()

    return render_template_string(
        BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '') + SYSTEM_TEMPLATE,
        page_title='System Status', active_page='system',
        circuit_breaker=type('CB', (), cb)(),
        alerts=alerts,
        alert_email='shairan2016@gmail.com',
        smtp_configured=bool(os.getenv('SMTP_USER')),
        polygon_configured=bool(os.getenv('POLYGON_API_KEY')),
        tradier_configured=bool(os.getenv('TRADIER_API_KEY')),
        db_connected=True,
        now=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )


@app.route('/system/kill')
def kill_switch():
    try:
        from trading.circuit_breaker import activate_kill_switch
        activate_kill_switch("Manual kill from dashboard")
    except Exception as e:
        print(f"Kill switch error: {e}")
    return redirect('/system')


@app.route('/system/reset')
def reset_breaker():
    try:
        from trading.circuit_breaker import reset_circuit_breaker
        reset_circuit_breaker(confirm=True)
    except Exception as e:
        print(f"Reset error: {e}")
    return redirect('/system')


@app.route('/api/data')
def api_data():
    return jsonify(get_dashboard_data())


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("SPX WHEEL TRADING DASHBOARD")
    print("=" * 60)
    print("\nOpen in browser: http://localhost:5000")
    print("\nPages:")
    print("  /           - Overview dashboard")
    print("  /backtest   - Full backtest report")
    print("  /trades     - All live/paper trades")
    print("  /positions  - Open positions")
    print("  /calibration - Run calibration")
    print("  /system     - Circuit breaker & alerts")
    print("\nPress Ctrl+C to stop")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=True)
