'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, AlertCircle, TrendingUp, DollarSign, Activity, CheckCircle, XCircle } from 'lucide-react'

interface DealerMechanicsDeepDiveProps {
  netGex: number
  volumeRatio: number
  currentPrice: number
  strikePrice: number
  openInterest: number
  volume: number
}

export default function DealerMechanicsDeepDive({
  netGex,
  volumeRatio,
  currentPrice,
  strikePrice,
  openInterest,
  volume
}: DealerMechanicsDeepDiveProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const volumeOIRatio = openInterest > 0 ? volume / openInterest : 0

  return (
    <div className="bg-gradient-to-br from-gray-900 to-gray-800 border-2 border-blue-500/30 rounded-xl overflow-hidden">
      {/* Header - Always Visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-6 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <AlertCircle className="w-6 h-6 text-blue-400" />
          <div className="text-left">
            <h2 className="text-xl font-bold text-white">
              🎓 DEALER MECHANICS DEEP DIVE
            </h2>
            <p className="text-sm text-gray-400 mt-1">
              EXACTLY why dealers MUST act, what triggers it, and WHERE we profit
            </p>
          </div>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-6 h-6 text-blue-400" />
        ) : (
          <ChevronDown className="w-6 h-6 text-blue-400" />
        )}
      </button>

      {/* Expandable Content */}
      {isExpanded && (
        <div className="p-6 pt-0 space-y-6 text-gray-300">

          {/* STEP 1: How Dealers Become Short Gamma */}
          <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-purple-500">
            <h3 className="text-lg font-bold text-purple-400 mb-3 flex items-center gap-2">
              <span className="bg-purple-500 text-white rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold">1</span>
              How Dealers Become Short Gamma (The Setup)
            </h3>

            <div className="space-y-3 text-sm">
              <div className="bg-gray-900/50 rounded p-3">
                <p className="font-semibold text-white mb-2">What happens:</p>
                <ul className="space-y-1 ml-4">
                  <li>• YOU buy 1 SPY ${strikePrice.toFixed(0)} call from dealer</li>
                  <li>• Dealer is now SHORT 1 call option</li>
                  <li>• Dealer has obligation to deliver 100 shares at ${strikePrice.toFixed(0)} if exercised</li>
                </ul>
              </div>

              <div className="bg-gray-900/50 rounded p-3">
                <p className="font-semibold text-white mb-2">Now scale this:</p>
                <ul className="space-y-1 ml-4">
                  <li>• Dealer sells {openInterest.toLocaleString()} of these calls (open interest)</li>
                  <li>• Total delta exposure: {(openInterest * 30).toLocaleString()} shares</li>
                  <li>• <span className="text-red-400 font-bold">Dealer is now SHORT GAMMA</span></li>
                </ul>
              </div>
            </div>
          </div>

          {/* STEP 2: What Creates the MUST */}
          <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-orange-500">
            <h3 className="text-lg font-bold text-orange-400 mb-3 flex items-center gap-2">
              <span className="bg-orange-500 text-white rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold">2</span>
              What Creates the "MUST"? (The Trigger)
            </h3>

            <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4 mb-4">
              <p className="text-orange-300 font-bold text-center text-lg">
                IT'S NOT THE ORDERS - IT'S THE PRICE MOVEMENT!
              </p>
            </div>

            <div className="space-y-3 text-sm">
              <p className="text-white">
                As SPY moves from ${(currentPrice - 5).toFixed(0)} → ${currentPrice.toFixed(0)}, the dealer's delta exposure GROWS:
              </p>

              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="bg-gray-900">
                    <tr>
                      <th className="p-2 text-left">SPY Price</th>
                      <th className="p-2 text-left">Delta/Contract</th>
                      <th className="p-2 text-left">Total Shares</th>
                      <th className="p-2 text-left">Exposure Value</th>
                    </tr>
                  </thead>
                  <tbody className="font-mono">
                    {[0, 1, 2, 3, 4, 5].map((i) => {
                      const price = currentPrice - 5 + i
                      const delta = 0.30 + (i * 0.07)
                      const shares = Math.round(openInterest * delta * 100)
                      const value = (shares * price / 1e6).toFixed(1)
                      return (
                        <tr key={i} className={`border-t border-gray-800 ${i === 5 ? 'bg-red-500/10 text-red-400' : ''}`}>
                          <td className="p-2">${price.toFixed(0)}</td>
                          <td className="p-2">-{delta.toFixed(2)}</td>
                          <td className="p-2">-{shares.toLocaleString()}</td>
                          <td className="p-2">-${value}M</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              <div className="bg-red-500/10 border border-red-500/30 rounded p-3 mt-3">
                <p className="text-red-300 font-bold">NOTICE:</p>
                <ul className="space-y-1 ml-4 mt-2">
                  <li>• NO NEW TRADES occurred</li>
                  <li>• Same {openInterest.toLocaleString()} short calls</li>
                  <li>• But exposure grew 2x JUST FROM PRICE MOVEMENT</li>
                  <li className="text-yellow-400">• <strong>This is GAMMA at work - delta moves AGAINST dealer</strong></li>
                </ul>
              </div>
            </div>
          </div>

          {/* STEP 3: Why They MUST Hedge */}
          <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-red-500">
            <h3 className="text-lg font-bold text-red-400 mb-3 flex items-center gap-2">
              <span className="bg-red-500 text-white rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold">3</span>
              Why Dealers MUST Hedge (The Forcing Function)
            </h3>

            <div className="space-y-3 text-sm">
              <div className="bg-gray-900/50 rounded p-3">
                <p className="font-semibold text-white mb-2">Trading desk has HARD LIMITS:</p>
                <ul className="space-y-1 ml-4">
                  <li>• Max gross delta: ±$50M</li>
                  <li>• Max net delta: ±$10M</li>
                  <li>• Breach = <span className="text-red-400 font-bold">auto-liquidation by risk systems</span></li>
                </ul>
              </div>

              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded p-4">
                <p className="text-yellow-300 font-bold mb-3">Timeline as SPY rallies:</p>
                <div className="space-y-2 font-mono text-xs">
                  <div>
                    <div className="text-green-400">09:30 AM - SPY at ${(currentPrice - 5).toFixed(0)}</div>
                    <div className="ml-4 text-gray-400">Delta: -$17.7M</div>
                    <div className="ml-4 text-green-400">✅ OK (35% of limit)</div>
                  </div>
                  <div className="border-t border-gray-700 pt-2">
                    <div className="text-yellow-400">10:15 AM - SPY at ${(currentPrice - 3).toFixed(0)}</div>
                    <div className="ml-4 text-gray-400">Delta: -$24.3M</div>
                    <div className="ml-4 text-yellow-400">⚠️ WARNING (49% of limit)</div>
                  </div>
                  <div className="border-t border-gray-700 pt-2">
                    <div className="text-orange-400">11:00 AM - SPY at ${(currentPrice - 1).toFixed(0)}</div>
                    <div className="ml-4 text-gray-400">Delta: -$32.7M</div>
                    <div className="ml-4 text-orange-400">🚨 ALERT (65% of limit)</div>
                  </div>
                  <div className="border-t border-gray-700 pt-2">
                    <div className="text-red-400">11:30 AM - SPY at ${currentPrice.toFixed(0)}</div>
                    <div className="ml-4 text-gray-400">Delta: -$37.5M</div>
                    <div className="ml-4 text-red-400">🔴 CRITICAL (75% of limit)</div>
                    <div className="ml-4 text-red-400 font-bold">⚡ AUTO-HEDGE TRIGGERED</div>
                    <div className="ml-4 text-white">→ BUY 25,000 shares SPY</div>
                  </div>
                </div>
              </div>

              <div className="bg-blue-500/10 border border-blue-500/30 rounded p-3">
                <p className="text-blue-300 font-bold mb-2">THE "MUST" COMES FROM:</p>
                <ul className="space-y-1 ml-4">
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />Regulatory capital requirements (SEC Rule 15c3-1)</li>
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />Firm risk limits (enforced by automated systems)</li>
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />Margin requirements (each $1 delta needs $0.50 margin)</li>
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />Mathematical inevitability (gamma compounds)</li>
                </ul>
                <p className="mt-3 text-white font-bold text-center">
                  They don't have a choice - systems FORCE the hedge!
                </p>
              </div>
            </div>
          </div>

          {/* STEP 4: WHERE We Take Advantage */}
          <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-green-500">
            <h3 className="text-lg font-bold text-green-400 mb-3 flex items-center gap-2">
              <span className="bg-green-500 text-white rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold">4</span>
              WHERE We Take Advantage (The Profit Mechanism)
            </h3>

            <div className="space-y-4 text-sm">
              <div className="bg-gradient-to-r from-green-500/20 to-blue-500/20 border border-green-500/30 rounded-lg p-4">
                <p className="text-green-300 font-bold text-lg mb-3 text-center">
                  🎯 KEY INSIGHT: Dealers hedge UP but SELL at the strike
                </p>
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <div className="bg-gray-900/50 rounded p-3">
                    <p className="text-green-400 font-bold mb-2">Below ${strikePrice.toFixed(0)}:</p>
                    <ul className="space-y-1 text-xs">
                      <li>• ${(strikePrice - 5).toFixed(0)} → ${(strikePrice - 4).toFixed(0)}: Buy 5K shares</li>
                      <li>• ${(strikePrice - 4).toFixed(0)} → ${(strikePrice - 3).toFixed(0)}: Buy 6K shares</li>
                      <li>• ${(strikePrice - 3).toFixed(0)} → ${(strikePrice - 2).toFixed(0)}: Buy 7K shares</li>
                      <li className="text-green-400 font-bold">→ Creates BUY pressure</li>
                    </ul>
                  </div>
                  <div className="bg-gray-900/50 rounded p-3">
                    <p className="text-red-400 font-bold mb-2">At ${strikePrice.toFixed(0)}:</p>
                    <ul className="space-y-1 text-xs">
                      <li>• Retail takes profit</li>
                      <li>• They SELL calls back</li>
                      <li>• Dealer must SELL shares</li>
                      <li className="text-red-400 font-bold">→ Creates ceiling</li>
                    </ul>
                  </div>
                </div>
              </div>

              <div className="bg-gray-900/50 rounded p-4">
                <p className="text-white font-bold mb-3">WHERE WE PROFIT:</p>
                <div className="space-y-2 ml-4">
                  <div className="flex items-start gap-2">
                    <DollarSign className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                    <span>Sell ${strikePrice.toFixed(0)}/${(strikePrice + 5).toFixed(0)} call spread when price approaches ${strikePrice.toFixed(0)}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <DollarSign className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                    <span>Bet that dealer sell pressure creates ceiling at ${strikePrice.toFixed(0)}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <DollarSign className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                    <span>Collect theta as time passes (time kills option value)</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <DollarSign className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
                    <span>Exit at 50% profit in 2-3 days</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* STEP 5: Volume/OI Ratio Explained */}
          <div className="bg-gray-950/50 rounded-lg p-5 border-l-4 border-cyan-500">
            <h3 className="text-lg font-bold text-cyan-400 mb-3 flex items-center gap-2">
              <span className="bg-cyan-500 text-white rounded-full w-7 h-7 flex items-center justify-center text-sm font-bold">5</span>
              Volume/OI Ratio - What It ACTUALLY Tells Us
            </h3>

            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-900/50 rounded p-3">
                  <p className="text-gray-400 text-xs mb-1">Volume Today</p>
                  <p className="text-2xl font-bold text-white">{volume.toLocaleString()}</p>
                  <p className="text-xs text-gray-500 mt-1">Contracts traded today</p>
                </div>
                <div className="bg-gray-900/50 rounded p-3">
                  <p className="text-gray-400 text-xs mb-1">Open Interest</p>
                  <p className="text-2xl font-bold text-white">{openInterest.toLocaleString()}</p>
                  <p className="text-xs text-gray-500 mt-1">Existing contracts</p>
                </div>
              </div>

              <div className="bg-cyan-500/10 border border-cyan-500/30 rounded p-4">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-cyan-300 font-bold">Volume/OI Ratio:</p>
                  <p className="text-3xl font-bold text-cyan-400">{volumeOIRatio.toFixed(1)}x</p>
                </div>
                <p className="text-white">
                  This means the {openInterest.toLocaleString()} existing contracts changed hands {volumeOIRatio.toFixed(1)} times today
                </p>
              </div>

              <div className="bg-gray-900/50 rounded p-3">
                <p className="text-white font-bold mb-2">What this ratio means:</p>
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <XCircle className="w-4 h-4 text-gray-500" />
                    <span><strong>0.5x:</strong> Static positions, no dealer activity</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-blue-400" />
                    <span><strong>1.0x:</strong> Normal activity, some hedging</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-yellow-400" />
                    <span><strong>2.0x+:</strong> Heavy activity - dealers actively hedging</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-400" />
                    <span><strong>5.0x+:</strong> Extreme activity - massive repositioning</span>
                  </div>
                </div>
              </div>

              <div className="bg-green-500/10 border border-green-500/30 rounded p-3">
                <p className="text-green-300 font-bold mb-2">Why {volumeOIRatio.toFixed(1)}x confirms our edge:</p>
                <ul className="space-y-1 ml-4">
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />Dealers are actively managing positions</li>
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />Retail is trading heavily at this strike</li>
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />${strikePrice.toFixed(0)} is the ACTIVE price level</li>
                  <li><CheckCircle className="w-4 h-4 inline mr-1 text-green-400" />This is where the "battle" is happening</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Summary */}
          <div className="bg-gradient-to-br from-purple-500/20 to-pink-500/20 border-2 border-purple-500/30 rounded-lg p-5">
            <h3 className="text-xl font-bold text-white mb-4 text-center">
              🎯 THE COMPLETE PICTURE
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div className="space-y-2">
                <p className="text-purple-400 font-bold">The Trigger:</p>
                <ul className="space-y-1 ml-4">
                  <li>✓ Price movement (not orders!)</li>
                  <li>✓ Gamma makes delta grow exponentially</li>
                  <li>✓ Risk systems auto-trigger hedging</li>
                </ul>
              </div>

              <div className="space-y-2">
                <p className="text-pink-400 font-bold">The Ceiling:</p>
                <ul className="space-y-1 ml-4">
                  <li>✓ Dealer hedging creates buy pressure below</li>
                  <li>✓ Profit taking + selling at strike</li>
                  <li>✓ Volume confirms ({volumeOIRatio.toFixed(1)}x OI)</li>
                </ul>
              </div>

              <div className="space-y-2">
                <p className="text-green-400 font-bold">Our Trade:</p>
                <ul className="space-y-1 ml-4">
                  <li>✓ Sell call spread at ${strikePrice.toFixed(0)}</li>
                  <li>✓ Collect theta + benefit from ceiling</li>
                  <li>✓ Exit at 50% profit (2-3 days)</li>
                </ul>
              </div>

              <div className="space-y-2">
                <p className="text-red-400 font-bold">Their Mistake:</p>
                <ul className="space-y-1 ml-4">
                  <li>✗ Buy calls at resistance</li>
                  <li>✗ Hold through rejection (greed)</li>
                  <li>✗ No stop loss (hope kills)</li>
                </ul>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-purple-500/30 text-center">
              <p className="text-white font-bold text-lg">
                Their Loss = Your Gain
              </p>
              <p className="text-gray-400 text-sm mt-1">
                Edge = Understanding mechanics they ignore
              </p>
            </div>
          </div>

        </div>
      )}
    </div>
  )
}
