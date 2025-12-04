'use client';

import React, { useState, useCallback, useEffect } from 'react';

// Types for the investor report
interface KeyMetric {
  value: number;
  format: 'percent' | 'currency' | 'decimal';
  label: string;
}

interface ExecutiveSummary {
  headline: string;
  key_metrics: Record<string, KeyMetric>;
  period_years: number;
  strategy_type: string;
}

interface StrategyComponent {
  name: string;
  allocation_pct: number;
  description: string;
  mechanics: string[];
  risk_profile: string;
}

interface InvestorReportData {
  meta: {
    report_version: string;
    generated_at: string;
    report_type: string;
  };
  header: {
    title: string;
    subtitle: string;
    period: string;
    initial_investment: number;
    final_value: number;
  };
  executive_summary: ExecutiveSummary;
  strategy_overview: {
    strategy_name: string;
    objective: string;
    components: StrategyComponent[];
    market_conditions: {
      best_environment: string;
      challenging_environment: string;
      adaptation: string;
    };
  };
  performance_analysis: {
    returns: {
      total_return_pct: number;
      cagr_pct: number;
      total_dollar_gain: number;
    };
    risk_adjusted: {
      sharpe_ratio: number;
      sharpe_interpretation: string;
      sortino_ratio: number;
      calmar_ratio: number;
    };
    drawdown_analysis: {
      max_drawdown_pct: number;
      max_drawdown_duration_days: number;
      context: string;
    };
  };
  income_analysis: {
    income_summary: {
      total_premium_collected: number;
      avg_monthly_income: number;
      annual_yield_pct: number;
    };
    income_consistency: {
      profitable_months_pct: number;
      interpretation: string;
    };
  };
  trade_statistics: {
    overall: {
      total_trades: number;
      winning_trades: number;
      losing_trades: number;
      win_rate_pct: number;
    };
    trade_quality: {
      profit_factor: number;
      expectancy_pct: number;
      avg_trade_duration_days: number;
    };
  };
  yearly_breakdown: {
    yearly_returns: Record<string, { return_pct: number; status: string }>;
    best_year: [string, number] | null;
    worst_year: [string, number] | null;
    positive_years: number;
    total_years: number;
  };
  key_observations: string[];
  disclosures: {
    backtest_limitations: string[];
    strategy_risks: string[];
    legal: string;
  };
}

interface InvestorReportProps {
  reportData?: InvestorReportData;
  onRunBacktest?: () => void;
  isLoading?: boolean;
}

// Format helpers
const formatValue = (value: number, format: string): string => {
  switch (format) {
    case 'percent':
      return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
    case 'currency':
      return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
    case 'decimal':
      return value.toFixed(2);
    default:
      return String(value);
  }
};

const formatCurrency = (value: number): string => {
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
};

const formatPercent = (value: number, showSign = false): string => {
  const sign = showSign && value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(1)}%`;
};

// Status badge component
const StatusBadge: React.FC<{ value: number; type: 'return' | 'risk' }> = ({ value, type }) => {
  let bgColor: string;
  let textColor: string;

  if (type === 'return') {
    bgColor = value >= 0 ? 'bg-green-900/30' : 'bg-red-900/30';
    textColor = value >= 0 ? 'text-green-400' : 'text-red-400';
  } else {
    bgColor = value < 15 ? 'bg-green-900/30' : value < 25 ? 'bg-yellow-900/30' : 'bg-red-900/30';
    textColor = value < 15 ? 'text-green-400' : value < 25 ? 'text-yellow-400' : 'text-red-400';
  }

  return (
    <span className={`px-2 py-1 rounded ${bgColor} ${textColor} text-sm font-mono`}>
      {formatPercent(value, type === 'return')}
    </span>
  );
};

// Main component
export const InvestorReport: React.FC<InvestorReportProps> = ({
  reportData,
  onRunBacktest,
  isLoading = false
}) => {
  const [activeTab, setActiveTab] = useState<'overview' | 'performance' | 'income' | 'risk'>('overview');

  if (isLoading) {
    return (
      <div className="bg-gray-900 rounded-lg p-8 text-center">
        <div className="animate-spin w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
        <p className="text-gray-400">Generating Investor Report...</p>
        <p className="text-gray-500 text-sm mt-2">Running backtest on historical data</p>
      </div>
    );
  }

  if (!reportData) {
    return (
      <div className="bg-gray-900 rounded-lg p-8 text-center">
        <div className="text-6xl mb-4">📊</div>
        <h3 className="text-xl font-semibold text-white mb-2">
          Combined Strategy Investor Report
        </h3>
        <p className="text-gray-400 mb-6 max-w-md mx-auto">
          Generate a professional investor-grade report for the Diagonal Put Spread +
          Cash-Secured Put Wheel combined strategy.
        </p>
        {onRunBacktest && (
          <button
            onClick={onRunBacktest}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
          >
            Generate Investor Report
          </button>
        )}
      </div>
    );
  }

  const { header, executive_summary, strategy_overview, performance_analysis, income_analysis, trade_statistics, yearly_breakdown, key_observations, disclosures } = reportData;

  return (
    <div className="bg-gray-900 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 p-6 border-b border-gray-800">
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-2xl font-bold text-white">{header.title}</h1>
            <p className="text-blue-400 mt-1">{header.subtitle}</p>
            <p className="text-gray-400 text-sm mt-2">{header.period}</p>
          </div>
          <div className="text-right">
            <div className="text-gray-400 text-sm">Initial Investment</div>
            <div className="text-white font-mono text-lg">{formatCurrency(header.initial_investment)}</div>
            <div className="text-gray-400 text-sm mt-2">Final Value</div>
            <div className="text-green-400 font-mono text-lg font-bold">{formatCurrency(header.final_value)}</div>
          </div>
        </div>
      </div>

      {/* Executive Summary */}
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-lg font-semibold text-white mb-4">Executive Summary</h2>
        <p className="text-xl text-green-400 mb-4">{executive_summary.headline}</p>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {Object.entries(executive_summary.key_metrics).map(([key, metric]) => (
            <div key={key} className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-gray-400 text-xs">{metric.label}</div>
              <div className={`text-lg font-mono font-bold ${
                metric.format === 'percent' && metric.value > 0 ? 'text-green-400' :
                metric.format === 'percent' && metric.value < 0 ? 'text-red-400' :
                'text-white'
              }`}>
                {formatValue(metric.value, metric.format)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex border-b border-gray-800">
        {(['overview', 'performance', 'income', 'risk'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-800/30'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Strategy Objective</h3>
              <p className="text-gray-300">{strategy_overview.objective}</p>
            </div>

            <div>
              <h3 className="text-lg font-semibold text-white mb-4">Strategy Components</h3>
              <div className="grid md:grid-cols-3 gap-4">
                {strategy_overview.components.map((comp, idx) => (
                  <div key={idx} className="bg-gray-800/50 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="font-semibold text-white">{comp.name}</h4>
                      <span className="text-blue-400 text-sm">{comp.allocation_pct}%</span>
                    </div>
                    <p className="text-gray-400 text-sm mb-3">{comp.description}</p>
                    <div className="space-y-1">
                      {comp.mechanics.map((m, i) => (
                        <div key={i} className="text-gray-500 text-xs flex items-start">
                          <span className="text-blue-400 mr-2">•</span>
                          {m}
                        </div>
                      ))}
                    </div>
                    <div className="mt-3 pt-3 border-t border-gray-700">
                      <span className="text-xs text-gray-500">Risk: </span>
                      <span className="text-xs text-gray-400">{comp.risk_profile}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="text-lg font-semibold text-white mb-2">Key Observations</h3>
              <ul className="space-y-2">
                {key_observations.map((obs, idx) => (
                  <li key={idx} className="flex items-start text-gray-300">
                    <span className="text-green-400 mr-2">✓</span>
                    {obs}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {activeTab === 'performance' && (
          <div className="space-y-6">
            <div className="grid md:grid-cols-2 gap-6">
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-semibold text-white mb-3">Returns</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Return</span>
                    <StatusBadge value={performance_analysis.returns.total_return_pct} type="return" />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">CAGR</span>
                    <span className="text-white font-mono">{formatPercent(performance_analysis.returns.cagr_pct)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Dollar Gain</span>
                    <span className="text-green-400 font-mono">{formatCurrency(performance_analysis.returns.total_dollar_gain)}</span>
                  </div>
                </div>
              </div>

              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-semibold text-white mb-3">Risk-Adjusted</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Sharpe Ratio</span>
                    <span className="text-white font-mono">{performance_analysis.risk_adjusted.sharpe_ratio.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Sortino Ratio</span>
                    <span className="text-white font-mono">{performance_analysis.risk_adjusted.sortino_ratio.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Calmar Ratio</span>
                    <span className="text-white font-mono">{performance_analysis.risk_adjusted.calmar_ratio.toFixed(2)}</span>
                  </div>
                </div>
                <p className="text-gray-500 text-xs mt-3">{performance_analysis.risk_adjusted.sharpe_interpretation}</p>
              </div>
            </div>

            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="font-semibold text-white mb-3">Yearly Returns</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {Object.entries(yearly_breakdown.yearly_returns).map(([year, data]) => (
                  <div key={year} className="text-center p-2 rounded bg-gray-900/50">
                    <div className="text-gray-400 text-sm">{year}</div>
                    <div className={`font-mono font-bold ${data.status === 'positive' ? 'text-green-400' : 'text-red-400'}`}>
                      {formatPercent(data.return_pct, true)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex justify-between text-sm">
                <span className="text-gray-400">
                  {yearly_breakdown.positive_years} of {yearly_breakdown.total_years} years positive
                </span>
                {yearly_breakdown.best_year && (
                  <span className="text-green-400">
                    Best: {yearly_breakdown.best_year[0]} ({formatPercent(yearly_breakdown.best_year[1], true)})
                  </span>
                )}
              </div>
            </div>

            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="font-semibold text-white mb-3">Trade Statistics</h3>
              <div className="grid md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Trades</span>
                    <span className="text-white font-mono">{trade_statistics.overall.total_trades}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Win Rate</span>
                    <span className="text-green-400 font-mono">{formatPercent(trade_statistics.overall.win_rate_pct)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Winning Trades</span>
                    <span className="text-green-400 font-mono">{trade_statistics.overall.winning_trades}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Losing Trades</span>
                    <span className="text-red-400 font-mono">{trade_statistics.overall.losing_trades}</span>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Profit Factor</span>
                    <span className="text-white font-mono">{trade_statistics.trade_quality.profit_factor.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Expectancy</span>
                    <span className="text-green-400 font-mono">{formatPercent(trade_statistics.trade_quality.expectancy_pct)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Avg Duration</span>
                    <span className="text-white font-mono">{trade_statistics.trade_quality.avg_trade_duration_days.toFixed(0)} days</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'income' && (
          <div className="space-y-6">
            <div className="grid md:grid-cols-3 gap-4">
              <div className="bg-gradient-to-br from-green-900/30 to-green-800/10 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Total Premium Collected</div>
                <div className="text-2xl font-bold text-green-400 font-mono">
                  {formatCurrency(income_analysis.income_summary.total_premium_collected)}
                </div>
              </div>
              <div className="bg-gradient-to-br from-blue-900/30 to-blue-800/10 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Average Monthly Income</div>
                <div className="text-2xl font-bold text-blue-400 font-mono">
                  {formatCurrency(income_analysis.income_summary.avg_monthly_income)}
                </div>
              </div>
              <div className="bg-gradient-to-br from-purple-900/30 to-purple-800/10 rounded-lg p-4">
                <div className="text-gray-400 text-sm">Annual Yield on Capital</div>
                <div className="text-2xl font-bold text-purple-400 font-mono">
                  {formatPercent(income_analysis.income_summary.annual_yield_pct)}
                </div>
              </div>
            </div>

            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="font-semibold text-white mb-3">Income Consistency</h3>
              <div className="flex items-center gap-4 mb-2">
                <div className="flex-1 bg-gray-700 rounded-full h-3">
                  <div
                    className="bg-green-500 h-3 rounded-full transition-all"
                    style={{ width: `${income_analysis.income_consistency.profitable_months_pct}%` }}
                  />
                </div>
                <span className="text-white font-mono">
                  {formatPercent(income_analysis.income_consistency.profitable_months_pct)}
                </span>
              </div>
              <p className="text-gray-400 text-sm">{income_analysis.income_consistency.interpretation}</p>
            </div>

            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="font-semibold text-white mb-3">Yield Comparison</h3>
              <div className="space-y-3">
                {[
                  { name: 'This Strategy', yield: income_analysis.income_summary.annual_yield_pct, highlight: true },
                  { name: '10-Year Treasury', yield: 5.0, highlight: false },
                  { name: 'S&P 500 Dividend', yield: 1.5, highlight: false },
                  { name: 'High Yield Bonds', yield: 7.0, highlight: false },
                ].map((item, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <div className="w-32 text-gray-400 text-sm">{item.name}</div>
                    <div className="flex-1 bg-gray-700 rounded h-4">
                      <div
                        className={`h-4 rounded ${item.highlight ? 'bg-green-500' : 'bg-gray-500'}`}
                        style={{ width: `${Math.min(100, item.yield * 5)}%` }}
                      />
                    </div>
                    <div className={`w-16 text-right font-mono ${item.highlight ? 'text-green-400 font-bold' : 'text-gray-400'}`}>
                      {formatPercent(item.yield)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'risk' && (
          <div className="space-y-6">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-semibold text-white mb-3">Drawdown Analysis</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Maximum Drawdown</span>
                    <StatusBadge value={performance_analysis.drawdown_analysis.max_drawdown_pct} type="risk" />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Max DD Duration</span>
                    <span className="text-white font-mono">{performance_analysis.drawdown_analysis.max_drawdown_duration_days} days</span>
                  </div>
                </div>
                <p className="text-gray-500 text-xs mt-3">{performance_analysis.drawdown_analysis.context}</p>
              </div>

              <div className="bg-gray-800/50 rounded-lg p-4">
                <h3 className="font-semibold text-white mb-3">Risk-Adjusted Metrics</h3>
                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-gray-400">Sharpe Ratio</span>
                      <span className="text-white font-mono">{performance_analysis.risk_adjusted.sharpe_ratio.toFixed(2)}</span>
                    </div>
                    <div className="w-full bg-gray-700 rounded h-2">
                      <div
                        className="bg-blue-500 h-2 rounded"
                        style={{ width: `${Math.min(100, performance_analysis.risk_adjusted.sharpe_ratio * 33)}%` }}
                      />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-1">
                      <span className="text-gray-400">Sortino Ratio</span>
                      <span className="text-white font-mono">{performance_analysis.risk_adjusted.sortino_ratio.toFixed(2)}</span>
                    </div>
                    <div className="w-full bg-gray-700 rounded h-2">
                      <div
                        className="bg-purple-500 h-2 rounded"
                        style={{ width: `${Math.min(100, performance_analysis.risk_adjusted.sortino_ratio * 33)}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-lg p-4">
              <h3 className="font-semibold text-yellow-400 mb-3">Risk Disclosures</h3>
              <div className="space-y-2">
                {disclosures.strategy_risks.map((risk, idx) => (
                  <div key={idx} className="flex items-start text-gray-300 text-sm">
                    <span className="text-yellow-500 mr-2">⚠</span>
                    {risk}
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-gray-800/50 rounded-lg p-4">
              <h3 className="font-semibold text-white mb-3">Backtest Limitations</h3>
              <ul className="space-y-1">
                {disclosures.backtest_limitations.map((item, idx) => (
                  <li key={idx} className="text-gray-400 text-sm flex items-start">
                    <span className="text-gray-500 mr-2">•</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            <div className="text-gray-500 text-xs italic border-t border-gray-800 pt-4">
              {disclosures.legal}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default InvestorReport;
