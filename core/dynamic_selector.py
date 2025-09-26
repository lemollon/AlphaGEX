"""
Dynamic Symbol Selection Module - Phase 1
==========================================
Additive enhancement that preserves all existing functionality while adding:
- Options volume-based ranking
- Market regime adaptation
- Volatility-based prioritization
- Strategic symbol classification
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import time

class DynamicSymbolSelector:
    """Dynamic symbol selection that enhances existing static lists"""
    
    def __init__(self, static_high_priority: List[str], static_medium_priority: List[str], 
                 static_extended: List[str]):
        """Initialize with existing static symbol lists"""
        
        # Preserve original static lists
        self.static_high_priority = static_high_priority
        self.static_medium_priority = static_medium_priority  
        self.static_extended = static_extended
        self.static_full_universe = static_high_priority + static_medium_priority + static_extended
        
        # Remove duplicates while preserving order
        self.static_full_universe = list(dict.fromkeys(self.static_full_universe))
        
        # Strategy-specific symbol classifications
        self.defensive_stocks = [
            "KO", "PEP", "WMT", "PG", "JNJ", "UNH", "NEE", "DUK", "SO", "D",
            "XLU", "XLP", "VZ", "T", "MMM", "KMB", "CL", "GIS", "K", "TLT",
            "COST", "HD", "LOW", "ABT", "CVS", "CI", "AEP", "EXC"
        ]
        
        self.high_gamma_candidates = [
            "TSLA", "NVDA", "AMD", "RIVN", "LCID", "PLTR", "RBLX", "COIN", "HOOD",
            "ZM", "ROKU", "DDOG", "SNOW", "CRWD", "OKTA", "SHOP", "TWLO", "PANW",
            "META", "NFLX", "CRM", "ADBE", "NOW", "WDAY", "VEEV"
        ]
        
        self.iron_condor_candidates = [
            "SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "XLV", "AAPL", "MSFT",
            "JPM", "BAC", "KO", "PEP", "JNJ", "PG", "HD", "MCD", "WMT"
        ]
        
        # Cache for volume and volatility data
        self.last_update = None
        self.cached_rankings = None
        self.cache_duration = timedelta(hours=6)  # Refresh every 6 hours
        
    def get_market_regime(self) -> str:
        """Determine current market regime for symbol prioritization"""
        try:
            # Get market indicators
            vix = yf.Ticker("^VIX")
            spy = yf.Ticker("SPY")
            
            vix_data = vix.history(period="5d")
            spy_data = spy.history(period="20d")
            
            if vix_data.empty or spy_data.empty:
                return "NEUTRAL"
                
            current_vix = vix_data['Close'].iloc[-1]
            spy_return = (spy_data['Close'].iloc[-1] / spy_data['Close'].iloc[0] - 1) * 100
            
            print(f"📊 Market Regime Analysis: VIX={current_vix:.1f}, SPY 20d={spy_return:.1f}%")
            
            # Determine regime
            if current_vix > 25:
                return "HIGH_VOLATILITY"
            elif spy_return < -5:
                return "BEAR"
            elif spy_return > 5:
                return "BULL"
            else:
                return "NEUTRAL"
                
        except Exception as e:
            print(f"⚠️ Error determining market regime: {e}")
            return "NEUTRAL"
    
    def get_volatility_metrics(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get volatility metrics for symbol ranking"""
        metrics = {}
        
        print(f"📈 Calculating volatility metrics for {len(symbols)} symbols...")
        
        for i, symbol in enumerate(symbols):
            try:
                if i % 20 == 0:  # Progress indicator
                    print(f"   Processing {i+1}/{len(symbols)}: {symbol}")
                    
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="30d")
                
                if len(hist) < 5:
                    continue
                    
                # Calculate key metrics
                returns = hist['Close'].pct_change().dropna()
                current_price = hist['Close'].iloc[-1]
                
                # Realized volatility (annualized)
                realized_vol = returns.std() * np.sqrt(252) * 100 if len(returns) > 1 else 0
                
                # Price movement over 20 days
                price_20d_ago = hist['Close'].iloc[0]
                price_change_20d = (current_price / price_20d_ago - 1) * 100
                
                # Trading range (for iron condor suitability)
                high_20d = hist['High'].max()
                low_20d = hist['Low'].min()
                range_pct = (high_20d / low_20d - 1) * 100
                
                # Average volume
                avg_volume = hist['Volume'].mean()
                
                metrics[symbol] = {
                    'realized_vol': realized_vol,
                    'price_change_20d': price_change_20d,
                    'range_pct': range_pct,
                    'current_price': current_price,
                    'avg_volume': avg_volume
                }
                
            except Exception as e:
                print(f"⚠️ Error getting data for {symbol}: {e}")
                continue
                
        print(f"✅ Volatility metrics calculated for {len(metrics)} symbols")
        return metrics
    
    def calculate_symbol_scores(self, symbols: List[str], market_regime: str) -> Dict[str, float]:
        """Calculate dynamic scores for symbol ranking"""
        
        # Get volatility metrics
        vol_metrics = self.get_volatility_metrics(symbols)
        
        scores = {}
        
        for symbol in symbols:
            score = 1.0  # Base score
            
            if symbol not in vol_metrics:
                scores[symbol] = score
                continue
                
            metrics = vol_metrics[symbol]
            
            # 1. Options volume proxy (based on known liquid names)
            if symbol in ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMD", "META"]:
                score += 3.0  # Highest volume names
            elif symbol in ["IWM", "DIA", "XLF", "XLE", "XLK", "XLV", "MSFT", "AMZN"]:
                score += 2.0  # High volume names
            elif symbol in self.high_gamma_candidates:
                score += 1.5  # High gamma potential
                
            # 2. Gamma exposure potential
            if symbol in self.high_gamma_candidates:
                score += 2.0
                
            # High volatility indicates gamma potential
            if metrics['realized_vol'] > 60:
                score += 2.0
            elif metrics['realized_vol'] > 40:
                score += 1.0
            elif metrics['realized_vol'] > 25:
                score += 0.5
                
            # Recent significant moves indicate active options
            abs_price_change = abs(metrics['price_change_20d'])
            if abs_price_change > 20:
                score += 1.5
            elif abs_price_change > 10:
                score += 1.0
            elif abs_price_change > 5:
                score += 0.5
                
            # 3. Market regime adjustments
            if market_regime == "BEAR":
                if symbol in self.defensive_stocks:
                    score += 1.5  # Emphasize defensive stocks
                if symbol in ["VIX", "SQQQ", "SPXS", "TLT", "GLD"]:
                    score += 1.0  # Bear market beneficiaries
                    
            elif market_regime == "HIGH_VOLATILITY":
                if symbol in self.high_gamma_candidates:
                    score += 1.5  # High gamma names during vol spikes
                    
            elif market_regime == "BULL":
                if symbol in ["QQQ", "XLK", "NVDA", "TSLA", "AMD"]:
                    score += 1.0  # Tech leadership in bull markets
                    
            # 4. Iron condor suitability (keep low-vol names for condors)
            if symbol in self.iron_condor_candidates:
                # Range-bound behavior is good for condors
                if 5 < metrics['range_pct'] < 15 and metrics['realized_vol'] < 30:
                    score += 1.0
                    
            # 5. Volume filter (avoid illiquid names)
            if metrics['avg_volume'] < 100000:
                score *= 0.5  # Deprioritize low volume
                
            scores[symbol] = score
            
        return scores
    
    def get_dynamic_symbol_list(self, target_count: int = 200) -> Tuple[List[str], Dict]:
        """
        Get dynamically ranked symbol list while preserving all existing functionality
        Returns: (ranked_symbols, metadata)
        """
        
        # Check cache first
        if (self.last_update and self.cached_rankings and 
            datetime.now() - self.last_update < self.cache_duration):
            print("📋 Using cached dynamic rankings")
            return self.cached_rankings[:target_count], {"source": "cache"}
            
        print(f"🔄 Generating dynamic symbol rankings (target: {target_count} symbols)")
        
        # Determine market regime
        market_regime = self.get_market_regime()
        
        # Calculate scores for all symbols in static universe
        symbol_scores = self.calculate_symbol_scores(self.static_full_universe, market_regime)
        
        # Sort by score (highest first)
        ranked_symbols = sorted(symbol_scores.keys(), 
                              key=lambda x: symbol_scores[x], reverse=True)
        
        # Ensure we always include top priorities regardless of score
        essential_symbols = ["SPY", "QQQ", "IWM", "VIX", "AAPL", "TSLA", "NVDA"]
        final_list = []
        
        # Add essential symbols first
        for symbol in essential_symbols:
            if symbol in ranked_symbols:
                final_list.append(symbol)
                ranked_symbols.remove(symbol)
                
        # Add remaining symbols by score
        final_list.extend(ranked_symbols)
        
        # Cache the results
        self.cached_rankings = final_list
        self.last_update = datetime.now()
        
        metadata = {
            "market_regime": market_regime,
            "total_scored": len(symbol_scores),
            "update_time": self.last_update.isoformat(),
            "top_scores": {symbol: symbol_scores.get(symbol, 0) 
                          for symbol in final_list[:10]}
        }
        
        print(f"✅ Dynamic ranking complete. Market regime: {market_regime}")
        print(f"📊 Top 10: {final_list[:10]}")
        
        return final_list[:target_count], metadata
    
    def get_symbols_for_scan_type(self, scan_type: str) -> Tuple[List[str], Dict]:
        """
        Get symbols for different scan types with dynamic prioritization
        Maintains backward compatibility with existing scan types
        """
        
        if scan_type == "High Priority Only":
            # Use dynamic ranking of high priority symbols
            dynamic_list, metadata = self.get_dynamic_symbol_list(len(self.static_high_priority))
            return dynamic_list[:50], metadata
            
        elif scan_type == "Custom List":
            # Use top 20 from dynamic ranking
            dynamic_list, metadata = self.get_dynamic_symbol_list(50)
            return dynamic_list[:20], metadata
            
        else:  # "All Symbols (200+)"
            # Full dynamic ranking
            return self.get_dynamic_symbol_list(200)
    
    def get_fallback_symbols(self, scan_type: str) -> List[str]:
        """
        Fallback to static lists if dynamic selection fails
        Ensures app never breaks due to dynamic selection issues
        """
        if scan_type == "High Priority Only":
            return self.static_high_priority[:50]
        elif scan_type == "Custom List":
            return self.static_high_priority[:20]
        else:
            return self.static_full_universe[:200]

# Utility function to integrate with existing app
def create_dynamic_selector(high_priority_symbols, medium_priority_symbols, extended_symbols):
    """Factory function to create dynamic selector with existing symbol lists"""
    return DynamicSymbolSelector(high_priority_symbols, medium_priority_symbols, extended_symbols)
