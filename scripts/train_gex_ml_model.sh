#!/bin/bash
# Train the GEX Directional ML model
#
# This script:
# 1. Populates all required data tables (gex_daily, underlying_prices, vix_history)
# 2. Trains the ML model
# 3. Saves the model to models/gex_directional_model.joblib
#
# Usage:
#   ./scripts/train_gex_ml_model.sh [ticker] [start_date]
#
# Examples:
#   ./scripts/train_gex_ml_model.sh           # Default: SPY from 2020-01-01
#   ./scripts/train_gex_ml_model.sh SPY 2022-01-01

TICKER=${1:-SPY}
START_DATE=${2:-2020-01-01}

echo "========================================"
echo "GEX ML Model Training Pipeline"
echo "========================================"
echo "Ticker: $TICKER"
echo "Start Date: $START_DATE"
echo ""

# Step 1: Populate data tables
echo "Step 1: Populating data tables..."
python scripts/populate_ml_training_data.py --ticker "$TICKER" --start "$START_DATE"

if [ $? -ne 0 ]; then
    echo "ERROR: Data population failed!"
    exit 1
fi

echo ""

# Step 2: Train ML model
echo "Step 2: Training ML model..."
python quant/gex_directional_ml.py --ticker "$TICKER" --start "$START_DATE" --save "models/gex_directional_model.joblib"

if [ $? -ne 0 ]; then
    echo "ERROR: ML training failed!"
    exit 1
fi

echo ""
echo "========================================"
echo "SUCCESS! Model trained and saved."
echo "========================================"
echo ""
echo "Next: Run backtest with ML model enabled:"
echo "  python backtest/zero_dte_hybrid_fixed.py \\"
echo "    --strategy apache_directional \\"
echo "    --ticker $TICKER \\"
echo "    --start $START_DATE \\"
echo "    --capital 1000 \\"
echo "    --risk 5 \\"
echo "    --width 5 \\"
echo "    --slippage 0.03 \\"
echo "    --min-vix 15 \\"
echo "    --max-vix 25 \\"
echo "    --gex-regime positive"
