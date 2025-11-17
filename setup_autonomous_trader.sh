#!/bin/bash
# Autonomous Trader Setup Script
# This installs all dependencies and prepares the trader for deployment

set -e  # Exit on error

echo "================================================"
echo "🤖 AlphaGEX Autonomous Trader Setup"
echo "================================================"
echo ""

# Check Python version
echo "✓ Checking Python version..."
python3 --version || { echo "❌ Python 3 not found"; exit 1; }

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "✓ Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📦 Installing dependencies..."
echo "   This may take a few minutes..."

# Core dependencies
pip install pandas>=2.0.0
pip install numpy>=1.24.0
pip install scipy>=1.11.0
pip install requests>=2.31.0
pip install pytz>=2023.3

# Trading libraries
pip install yfinance>=0.2.52
pip install py_vollib>=1.0.1

# LangChain for AI reasoning
pip install anthropic>=0.16.0
pip install langchain>=0.1.0
pip install langchain-anthropic>=0.1.0
pip install langchain-community>=0.0.20
pip install pydantic>=2.5.0

# Scheduler
pip install apscheduler>=3.10.0

# Optional: scikit-learn for ML
pip install scikit-learn>=1.3.0

echo ""
echo "✅ All dependencies installed!"
echo ""

# Test imports
echo "🧪 Testing imports..."
python3 << EOF
try:
    from autonomous_paper_trader import AutonomousPaperTrader
    from autonomous_scheduler import run_autonomous_trader_cycle
    from autonomous_ai_reasoning import AutonomousAIReasoning
    from autonomous_risk_manager import AutonomousRiskManager
    print("✅ All imports successful!")
except Exception as e:
    print(f"❌ Import failed: {e}")
    exit(1)
EOF

echo ""
echo "================================================"
echo "✅ Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Test with: ./test_autonomous_trader.sh"
echo "2. Deploy with: ./deploy_autonomous_trader.sh"
echo "3. Monitor at: http://localhost:8000/api/autonomous/health"
echo ""
