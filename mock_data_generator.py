"""
Mock Data Generator for AlphaGEX Development
Generates realistic mock data for testing without consuming API quota
"""

import random
from datetime import datetime, timedelta
import numpy as np

class MockDataGenerator:
    """Generate realistic mock market data for development"""

    @staticmethod
    def generate_gex_data(symbol="SPY", spot_price=None):
        """Generate mock GEX data that looks realistic"""
        if spot_price is None:
            spot_price = random.uniform(580, 600)

        # Generate realistic GEX values
        net_gex = random.uniform(-3e9, 2e9)
        total_call_gex = abs(random.uniform(5e9, 15e9))
        total_put_gex = -abs(random.uniform(5e9, 15e9))

        # Flip point slightly below/above current price
        flip_point = spot_price + random.uniform(-10, 10)

        # Walls near key levels
        call_wall = spot_price + random.uniform(5, 15)
        put_wall = spot_price - random.uniform(5, 15)

        return {
            "symbol": symbol,
            "spot_price": spot_price,
            "total_call_gex": total_call_gex,
            "total_put_gex": total_put_gex,
            "net_gex": net_gex,
            "gex_flip_point": flip_point,
            "flip_point": flip_point,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "vix": random.uniform(12, 25),
            "key_levels": {
                "resistance": [spot_price + i * 5 for i in range(1, 4)],
                "support": [spot_price - i * 5 for i in range(1, 4)]
            },
            "timestamp": datetime.now().isoformat(),
            "_mock": True  # Flag to indicate mock data
        }

    @staticmethod
    def generate_gex_levels(symbol="SPY", spot_price=None, num_strikes=21):
        """Generate mock strike-level GEX data"""
        if spot_price is None:
            spot_price = random.uniform(580, 600)

        strikes = []
        strike_spacing = 5  # $5 strikes

        # Center strikes around spot price
        start_strike = int(spot_price - (num_strikes // 2) * strike_spacing)

        for i in range(num_strikes):
            strike = start_strike + i * strike_spacing
            distance_from_spot = strike - spot_price

            # More GEX near the money
            atm_factor = 1.0 / (1.0 + abs(distance_from_spot) / 20)

            call_gex = random.uniform(1e8, 5e8) * atm_factor
            put_gex = -random.uniform(1e8, 5e8) * atm_factor

            # Higher OI near the money
            call_oi = int(random.uniform(10000, 50000) * atm_factor)
            put_oi = int(random.uniform(10000, 50000) * atm_factor)

            strikes.append({
                "strike": strike,
                "call_gex": call_gex,
                "put_gex": put_gex,
                "total_gex": call_gex + put_gex,
                "call_oi": call_oi,
                "put_oi": put_oi,
                "pcr": put_oi / call_oi if call_oi > 0 else 1.0
            })

        return strikes

    @staticmethod
    def generate_psychology_regime(symbol="SPY", spot_price=None):
        """Generate mock psychology trap regime analysis"""
        if spot_price is None:
            spot_price = random.uniform(580, 600)

        regimes = [
            'LIBERATION_TRADE',
            'FALSE_FLOOR',
            'ZERO_DTE_PIN',
            'DESTINATION_TRADE',
            'PIN_AT_CALL_WALL',
            'EXPLOSIVE_CONTINUATION',
            'NEUTRAL'
        ]

        regime_type = random.choice(regimes)

        # Generate multi-timeframe RSI
        rsi_values = {
            '5m': random.uniform(30, 70),
            '15m': random.uniform(30, 70),
            '1h': random.uniform(30, 70),
            '4h': random.uniform(30, 70),
            '1d': random.uniform(30, 70)
        }

        overbought_count = sum(1 for v in rsi_values.values() if v > 70)
        oversold_count = sum(1 for v in rsi_values.values() if v < 30)

        # Calculate weighted RSI score
        weights = {'5m': 0.1, '15m': 0.15, '1h': 0.25, '4h': 0.25, '1d': 0.25}
        rsi_score = sum(rsi_values[tf] * weights[tf] for tf in rsi_values.keys()) - 50

        return {
            "timestamp": datetime.now().isoformat(),
            "spy_price": spot_price,
            "regime": {
                "primary_type": regime_type,
                "secondary_type": None,
                "confidence": random.uniform(60, 95),
                "description": f"Market showing {regime_type.replace('_', ' ').lower()} characteristics",
                "detailed_explanation": "Mock psychology regime analysis for development",
                "trade_direction": random.choice(['LONG', 'SHORT', 'NEUTRAL']),
                "risk_level": random.choice(['low', 'medium', 'high']),
                "timeline": random.choice(['1-2 days', '2-5 days', 'This week']),
                "price_targets": {},
                "psychology_trap": "Retail traders expecting continuation while institutions position for reversal",
                "supporting_factors": [
                    "Multi-timeframe RSI alignment",
                    "Gamma wall positioning",
                    "Volume profile analysis"
                ]
            },
            "rsi_analysis": {
                "score": rsi_score,
                "individual_rsi": rsi_values,
                "aligned_count": {
                    "overbought": overbought_count,
                    "oversold": oversold_count,
                    "extreme_overbought": sum(1 for v in rsi_values.values() if v > 80),
                    "extreme_oversold": sum(1 for v in rsi_values.values() if v < 20)
                },
                "coiling_detected": random.choice([True, False])
            },
            "current_walls": {
                "call_wall": {
                    "strike": spot_price + random.uniform(5, 15),
                    "distance_pct": random.uniform(1, 3),
                    "dealer_position": "short"
                },
                "put_wall": {
                    "strike": spot_price - random.uniform(5, 15),
                    "distance_pct": random.uniform(1, 3),
                    "dealer_position": "long"
                },
                "net_gamma": random.uniform(-3e9, 2e9),
                "net_gamma_regime": "short" if random.random() > 0.5 else "long"
            },
            "expiration_analysis": {},
            "forward_gex": {},
            "volume_ratio": random.uniform(0.8, 1.5),
            "alert_level": {
                "level": random.choice(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']),
                "reason": "Mock alert level for development"
            },
            "_mock": True  # Flag to indicate mock data
        }

    @staticmethod
    def generate_trading_guide(regime_type="LIBERATION_TRADE"):
        """Generate mock trading guide"""
        return {
            "strategy_name": regime_type.replace('_', ' ').title(),
            "recommended_direction": random.choice(['LONG', 'SHORT']),
            "entry_price": random.uniform(580, 600),
            "target_price": random.uniform(590, 610),
            "stop_loss": random.uniform(570, 590),
            "risk_reward_ratio": random.uniform(2, 4),
            "confidence_level": random.uniform(65, 90),
            "reasoning": "Mock trading guide for development testing",
            "key_factors": [
                "RSI alignment",
                "Gamma positioning",
                "Volume confirmation"
            ],
            "_mock": True
        }


# Convenience functions for quick access
def get_mock_gex(symbol="SPY"):
    """Quick function to get mock GEX data"""
    return MockDataGenerator.generate_gex_data(symbol)

def get_mock_psychology(symbol="SPY"):
    """Quick function to get mock psychology regime"""
    return MockDataGenerator.generate_psychology_regime(symbol)

def get_mock_levels(symbol="SPY"):
    """Quick function to get mock GEX levels"""
    spot = random.uniform(580, 600)
    return MockDataGenerator.generate_gex_levels(symbol, spot)
