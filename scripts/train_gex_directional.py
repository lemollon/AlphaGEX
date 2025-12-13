#!/usr/bin/env python3
"""
Train GEX Directional ML Model
==============================

This script trains an ML model to predict daily market direction
(BULLISH/BEARISH/FLAT) based on GEX structure at market open.

Usage:
    # Train with defaults (SPY, from 2022)
    python scripts/train_gex_directional.py

    # Train on specific ticker and date range
    python scripts/train_gex_directional.py --ticker SPX --start 2023-01-01

    # Save to custom path
    python scripts/train_gex_directional.py --save models/my_model.joblib

The trained model can be used for:
1. Directional trading bot decisions
2. Pre-market analysis of GEX patterns
3. Risk management (avoid trading in uncertain patterns)
"""

import os
import sys

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from quant.gex_directional_ml import GEXDirectionalPredictor, main

if __name__ == '__main__':
    main()
