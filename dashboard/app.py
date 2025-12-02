"""
SPX WHEEL TRADING DASHBOARD

This is the FRONTEND - where you SEE everything:
- Every trade with full details
- Every price and where it came from
- Current positions and their status
- Equity curve
- Data quality metrics
- Real-time performance vs backtest

Run with: python dashboard.py
Then open: http://localhost:5000
"""

import os
import sys
from datetime import datetime, timedelta
from flask import Flask, render_template_string, jsonify
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection

app = Flask(__name__)

# HTML Template - Complete Dashboard
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>SPX Wheel Trading Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #16213e, #0f3460);
            padding: 20px 40px;
            border-bottom: 3px solid #e94560;
        }
        .header h1 { font-size: 28px; }
        .header .subtitle { color: #888; margin-top: 5px; }

        .container { padding: 20px 40px; }

        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }

        .card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #0f3460;
        }
        .card.full { grid-column: 1 / -1; }
        .card.half { grid-column: span 2; }

        .card h2 {
            font-size: 14px;
            color: #888;
            text-transform: uppercase;
            margin-bottom: 10px;
        }
        .card .value {
            font-size: 32px;
            font-weight: bold;
        }
        .card .value.positive { color: #4ade80; }
        .card .value.negative { color: #f87171; }
        .card .value.warning { color: #fbbf24; }

        .data-quality {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .quality-bar {
            flex: 1;
            height: 20px;
            background: #0f3460;
            border-radius: 10px;
            overflow: hidden;
        }
        .quality-fill {
            height: 100%;
            background: linear-gradient(90deg, #f87171, #fbbf24, #4ade80);
            transition: width 0.5s;
        }
        .quality-label {
            font-size: 24px;
            font-weight: bold;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }
        th {
            color: #888;
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 600;
        }
        tr:hover { background: #0f3460; }

        .status-open { color: #4ade80; }
        .status-closed { color: #888; }

        .source-polygon { color: #4ade80; }
        .source-tradier { color: #60a5fa; }
        .source-estimated { color: #fbbf24; }

        .chart-container { height: 300px; }

        .trade-details {
            max-height: 400px;
            overflow-y: auto;
        }

        .refresh-info {
            text-align: right;
            color: #666;
            font-size: 12px;
            margin-top: 20px;
        }

        .alert {
            padding: 15px 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .alert.warning {
            background: rgba(251, 191, 36, 0.2);
            border: 1px solid #fbbf24;
            color: #fbbf24;
        }
        .alert.success {
            background: rgba(74, 222, 128, 0.2);
            border: 1px solid #4ade80;
            color: #4ade80;
        }
        .alert.danger {
            background: rgba(248, 113, 113, 0.2);
            border: 1px solid #f87171;
            color: #f87171;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>SPX Wheel Trading Dashboard</h1>
        <div class="subtitle">Real-time monitoring • Every trade logged • Full transparency</div>
    </div>

    <div class="container">
        <!-- Alerts -->
        {% if data_quality < 80 %}
        <div class="alert warning">
            ⚠️ DATA QUALITY WARNING: Only {{ "%.1f"|format(data_quality) }}% of prices are from real data.
            Results may not reflect actual trading performance.
        </div>
        {% endif %}

        {% if divergence and divergence|abs > 10 %}
        <div class="alert danger">
            🔴 PERFORMANCE DIVERGENCE: Live performance differs from backtest by {{ "%.1f"|format(divergence) }}%.
            Consider recalibrating parameters.
        </div>
        {% endif %}

        <!-- Summary Cards -->
        <div class="grid">
            <div class="card">
                <h2>Total Equity</h2>
                <div class="value {{ 'positive' if total_pnl >= 0 else 'negative' }}">
                    ${{ "{:,.2f}".format(total_equity) }}
                </div>
            </div>
            <div class="card">
                <h2>Total P&L</h2>
                <div class="value {{ 'positive' if total_pnl >= 0 else 'negative' }}">
                    {{ "+" if total_pnl >= 0 else "" }}${{ "{:,.2f}".format(total_pnl) }}
                </div>
            </div>
            <div class="card">
                <h2>Win Rate</h2>
                <div class="value {{ 'positive' if win_rate >= 70 else 'warning' if win_rate >= 50 else 'negative' }}">
                    {{ "%.1f"|format(win_rate) }}%
                </div>
            </div>
            <div class="card">
                <h2>Open Positions</h2>
                <div class="value">{{ open_positions }}</div>
            </div>
        </div>

        <!-- Data Quality -->
        <div class="grid">
            <div class="card full">
                <h2>Data Quality - How Much is REAL Data vs Estimated</h2>
                <div class="data-quality">
                    <div class="quality-bar">
                        <div class="quality-fill" style="width: {{ data_quality }}%"></div>
                    </div>
                    <div class="quality-label {{ 'positive' if data_quality >= 80 else 'warning' if data_quality >= 50 else 'negative' }}">
                        {{ "%.1f"|format(data_quality) }}%
                    </div>
                </div>
                <table>
                    <tr>
                        <td>Real Data Points (Polygon/Tradier)</td>
                        <td style="text-align:right;color:#4ade80">{{ real_data_points }}</td>
                    </tr>
                    <tr>
                        <td>Estimated Data Points (Formula)</td>
                        <td style="text-align:right;color:#fbbf24">{{ estimated_data_points }}</td>
                    </tr>
                </table>
            </div>
        </div>

        <!-- Calibrated Parameters -->
        <div class="grid">
            <div class="card half">
                <h2>Calibrated Parameters (from Backtest)</h2>
                <table>
                    <tr><td>Put Delta</td><td style="text-align:right">{{ params.put_delta }}</td></tr>
                    <tr><td>DTE Target</td><td style="text-align:right">{{ params.dte_target }} days</td></tr>
                    <tr><td>Max Margin</td><td style="text-align:right">{{ "%.0f"|format(params.max_margin_pct * 100) }}%</td></tr>
                    <tr><td>Calibrated On</td><td style="text-align:right">{{ params.calibration_date[:10] if params.calibration_date else 'Not calibrated' }}</td></tr>
                </table>
            </div>
            <div class="card half">
                <h2>Backtest vs Live Performance</h2>
                <table>
                    <tr>
                        <td></td>
                        <th style="text-align:right">Backtest</th>
                        <th style="text-align:right">Live</th>
                        <th style="text-align:right">Diff</th>
                    </tr>
                    <tr>
                        <td>Win Rate</td>
                        <td style="text-align:right">{{ "%.1f"|format(params.backtest_win_rate) }}%</td>
                        <td style="text-align:right">{{ "%.1f"|format(win_rate) }}%</td>
                        <td style="text-align:right" class="{{ 'positive' if (win_rate - params.backtest_win_rate)|abs < 5 else 'warning' if (win_rate - params.backtest_win_rate)|abs < 10 else 'negative' }}">
                            {{ "%+.1f"|format(win_rate - params.backtest_win_rate) }}%
                        </td>
                    </tr>
                    <tr>
                        <td>Expected Return</td>
                        <td style="text-align:right">{{ "%.1f"|format(params.backtest_total_return) }}%</td>
                        <td style="text-align:right">{{ "%.1f"|format(live_return_pct) }}%</td>
                        <td style="text-align:right" class="{{ 'positive' if (live_return_pct - params.backtest_total_return)|abs < 5 else 'warning' }}">
                            {{ "%+.1f"|format(live_return_pct - params.backtest_total_return) }}%
                        </td>
                    </tr>
                </table>
            </div>
        </div>

        <!-- Equity Curve -->
        <div class="grid">
            <div class="card full">
                <h2>Equity Curve</h2>
                <div class="chart-container">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Open Positions -->
        <div class="grid">
            <div class="card full">
                <h2>Open Positions</h2>
                <div class="trade-details">
                    <table>
                        <thead>
                            <tr>
                                <th>Ticker</th>
                                <th>Strike</th>
                                <th>Expiration</th>
                                <th>Contracts</th>
                                <th>Entry Price</th>
                                <th>Premium</th>
                                <th>Price Source</th>
                                <th>DTE</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for pos in positions if pos.status == 'OPEN' %}
                            <tr>
                                <td><strong>{{ pos.option_ticker }}</strong></td>
                                <td>${{ "{:,.0f}".format(pos.strike) }}</td>
                                <td>{{ pos.expiration }}</td>
                                <td>{{ pos.contracts }}</td>
                                <td>${{ "{:.2f}".format(pos.entry_price) }}</td>
                                <td>${{ "{:,.2f}".format(pos.premium_received) }}</td>
                                <td class="source-{{ pos.price_source|lower if pos.price_source else 'estimated' }}">
                                    {{ pos.price_source or 'ESTIMATED' }}
                                </td>
                                <td>{{ pos.dte }} days</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="8" style="text-align:center;color:#666">No open positions</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- Trade Log -->
        <div class="grid">
            <div class="card full">
                <h2>Complete Trade Log - Every Trade with Full Details</h2>
                <div class="trade-details">
                    <table>
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Date</th>
                                <th>Ticker</th>
                                <th>Strike</th>
                                <th>Entry</th>
                                <th>Exit</th>
                                <th>Premium</th>
                                <th>Settlement</th>
                                <th>P&L</th>
                                <th>Source</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for trade in all_trades %}
                            <tr>
                                <td>{{ trade.id }}</td>
                                <td>{{ trade.opened_at[:10] if trade.opened_at else '' }}</td>
                                <td><strong>{{ trade.option_ticker }}</strong></td>
                                <td>${{ "{:,.0f}".format(trade.strike) }}</td>
                                <td>${{ "{:.2f}".format(trade.entry_price) }}</td>
                                <td>{{ "$%.2f"|format(trade.exit_price) if trade.exit_price else '-' }}</td>
                                <td>${{ "{:,.2f}".format(trade.premium_received) }}</td>
                                <td class="{{ 'negative' if trade.settlement_pnl and trade.settlement_pnl < 0 else '' }}">
                                    {{ "$%,.2f"|format(trade.settlement_pnl) if trade.settlement_pnl else '-' }}
                                </td>
                                <td class="{{ 'positive' if trade.total_pnl and trade.total_pnl > 0 else 'negative' if trade.total_pnl and trade.total_pnl < 0 else '' }}">
                                    {{ "$%,.2f"|format(trade.total_pnl) if trade.total_pnl else '-' }}
                                </td>
                                <td class="source-{{ trade.price_source|lower if trade.price_source else 'estimated' }}">
                                    {{ trade.price_source or '?' }}
                                </td>
                                <td class="status-{{ trade.status|lower }}">{{ trade.status }}</td>
                            </tr>
                            {% else %}
                            <tr><td colspan="11" style="text-align:center;color:#666">No trades yet</td></tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="refresh-info">
            Last updated: {{ now }} • Auto-refreshes every 30 seconds
        </div>
    </div>

    <script>
        // Equity Chart
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
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { color: '#0f3460' },
                        ticks: { color: '#888' }
                    },
                    y: {
                        grid: { color: '#0f3460' },
                        ticks: {
                            color: '#888',
                            callback: function(value) {
                                return '$' + value.toLocaleString();
                            }
                        }
                    }
                }
            }
        });

        // Auto-refresh
        setTimeout(() => location.reload(), 30000);
    </script>
</body>
</html>
"""


def get_dashboard_data():
    """Fetch all data for the dashboard"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get all positions
        cursor.execute('''
            SELECT
                id, option_ticker, strike, expiration, contracts,
                entry_price, exit_price, premium_received, settlement_pnl, total_pnl,
                status, opened_at, closed_at, notes, parameters_used
            FROM spx_wheel_positions
            ORDER BY opened_at DESC
        ''')

        positions = []
        for row in cursor.fetchall():
            # Extract price source from parameters_used JSON
            params_json = row[14] or '{}'
            if isinstance(params_json, str):
                params_json = json.loads(params_json)
            price_source = params_json.get('price_source', 'ESTIMATED')

            # Calculate DTE
            exp = row[3]
            if exp:
                if isinstance(exp, str):
                    exp = datetime.strptime(exp, '%Y-%m-%d').date()
                dte = (exp - datetime.now().date()).days
            else:
                dte = 0

            positions.append({
                'id': row[0],
                'option_ticker': row[1],
                'strike': float(row[2] or 0),
                'expiration': str(row[3]),
                'contracts': row[4],
                'entry_price': float(row[5] or 0),
                'exit_price': float(row[6]) if row[6] else None,
                'premium_received': float(row[7] or 0),
                'settlement_pnl': float(row[8]) if row[8] else None,
                'total_pnl': float(row[9]) if row[9] else None,
                'status': row[10],
                'opened_at': str(row[11]) if row[11] else '',
                'closed_at': str(row[12]) if row[12] else '',
                'notes': row[13],
                'price_source': price_source,
                'dte': dte
            })

        # Count data quality
        real_count = sum(1 for p in positions if p['price_source'] in ['POLYGON', 'TRADIER_LIVE', 'POLYGON_HISTORICAL'])
        estimated_count = sum(1 for p in positions if p['price_source'] == 'ESTIMATED')
        total_points = real_count + estimated_count
        data_quality = (real_count / total_points * 100) if total_points > 0 else 100

        # Calculate summary stats
        closed_positions = [p for p in positions if p['status'] == 'CLOSED']
        open_positions_list = [p for p in positions if p['status'] == 'OPEN']

        total_pnl = sum(p['total_pnl'] or 0 for p in closed_positions)
        open_premium = sum(p['premium_received'] or 0 for p in open_positions_list)

        winners = sum(1 for p in closed_positions if (p['total_pnl'] or 0) > 0)
        win_rate = (winners / len(closed_positions) * 100) if closed_positions else 0

        initial_capital = 1000000
        total_equity = initial_capital + total_pnl + open_premium
        live_return_pct = ((total_equity - initial_capital) / initial_capital) * 100

        # Get parameters
        cursor.execute('''
            SELECT parameters FROM spx_wheel_parameters
            WHERE is_active = TRUE
            ORDER BY timestamp DESC LIMIT 1
        ''')
        params_row = cursor.fetchone()
        if params_row:
            params = params_row[0]
            if isinstance(params, str):
                params = json.loads(params)
        else:
            params = {
                'put_delta': 0.20,
                'dte_target': 45,
                'max_margin_pct': 0.50,
                'backtest_win_rate': 0,
                'backtest_total_return': 0,
                'calibration_date': ''
            }

        # Get equity curve
        cursor.execute('''
            SELECT date, equity, cumulative_pnl
            FROM spx_wheel_performance
            ORDER BY date
        ''')
        equity_curve = [
            {'date': str(row[0]), 'equity': float(row[1])}
            for row in cursor.fetchall()
        ]

        # If no equity curve, create from positions
        if not equity_curve and positions:
            equity = initial_capital
            for p in sorted(positions, key=lambda x: x['opened_at']):
                if p['status'] == 'CLOSED' and p['total_pnl']:
                    equity += p['total_pnl']
                    equity_curve.append({
                        'date': p['closed_at'][:10] if p['closed_at'] else '',
                        'equity': equity
                    })

        conn.close()

        # Calculate divergence
        divergence = win_rate - params.get('backtest_win_rate', 0) if closed_positions else 0

        return {
            'positions': positions,
            'all_trades': positions,  # Same data for trade log
            'open_positions': len(open_positions_list),
            'total_pnl': total_pnl,
            'total_equity': total_equity,
            'win_rate': win_rate,
            'live_return_pct': live_return_pct,
            'data_quality': data_quality,
            'real_data_points': real_count,
            'estimated_data_points': estimated_count,
            'params': type('Params', (), params)(),  # Convert dict to object
            'equity_curve': equity_curve,
            'divergence': divergence,
            'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    except Exception as e:
        print(f"Error fetching dashboard data: {e}")
        import traceback
        traceback.print_exc()

        # Return empty data
        return {
            'positions': [],
            'all_trades': [],
            'open_positions': 0,
            'total_pnl': 0,
            'total_equity': 1000000,
            'win_rate': 0,
            'live_return_pct': 0,
            'data_quality': 0,
            'real_data_points': 0,
            'estimated_data_points': 0,
            'params': type('Params', (), {
                'put_delta': 0.20, 'dte_target': 45, 'max_margin_pct': 0.50,
                'backtest_win_rate': 0, 'backtest_total_return': 0, 'calibration_date': ''
            })(),
            'equity_curve': [],
            'divergence': 0,
            'now': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }


@app.route('/')
def dashboard():
    """Main dashboard view"""
    data = get_dashboard_data()
    return render_template_string(DASHBOARD_HTML, **data)


@app.route('/api/data')
def api_data():
    """API endpoint for raw data"""
    data = get_dashboard_data()
    # Convert params object back to dict for JSON
    data['params'] = {
        'put_delta': data['params'].put_delta,
        'dte_target': data['params'].dte_target,
        'max_margin_pct': data['params'].max_margin_pct,
        'backtest_win_rate': data['params'].backtest_win_rate,
        'backtest_total_return': data['params'].backtest_total_return,
        'calibration_date': data['params'].calibration_date
    }
    return jsonify(data)


@app.route('/api/trades')
def api_trades():
    """API endpoint for all trades"""
    data = get_dashboard_data()
    return jsonify(data['all_trades'])


if __name__ == '__main__':
    print("\n" + "="*60)
    print("SPX WHEEL TRADING DASHBOARD")
    print("="*60)
    print("\nStarting dashboard server...")
    print("\nOpen in your browser: http://localhost:5000")
    print("\nFeatures:")
    print("  - Real-time position monitoring")
    print("  - Complete trade log with every detail")
    print("  - Data quality indicator (real vs estimated)")
    print("  - Equity curve visualization")
    print("  - Backtest vs live comparison")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=True)
