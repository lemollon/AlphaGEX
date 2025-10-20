"""
Test imports to verify all classes are accessible
"""

import sys
from pathlib import Path

# Add current directory to path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Test imports
try:
    from core_classes_and_engines import (
        TradingVolatilityAPI,
        MonteCarloEngine,
        BlackScholesPricer
    )
    print("✅ All imports successful!")
    print(f"TradingVolatilityAPI: {TradingVolatilityAPI}")
    print(f"MonteCarloEngine: {MonteCarloEngine}")
    print(f"BlackScholesPricer: {BlackScholesPricer}")
except ImportError as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
