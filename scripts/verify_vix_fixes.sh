#!/bin/bash
# =============================================================================
# VIX Fix Verification Script for Render
# =============================================================================
# Run this after deploying to verify all VIX fixes are working
#
# Usage: bash scripts/verify_vix_fixes.sh
# =============================================================================

set -e

echo "=============================================="
echo "  VIX FIX VERIFICATION SCRIPT"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

check() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}: $2"
        ((PASS++))
    else
        echo -e "${RED}✗ FAIL${NC}: $2"
        ((FAIL++))
    fi
}

warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# -----------------------------------------------------------------------------
# 1. Check yfinance is installed
# -----------------------------------------------------------------------------
echo ""
echo "1. Checking yfinance installation..."
python3 -c "import yfinance; print(f'   Version: {yfinance.__version__}')" 2>/dev/null
check $? "yfinance is installed"

# -----------------------------------------------------------------------------
# 2. Test Yahoo VIX fetch directly
# -----------------------------------------------------------------------------
echo ""
echo "2. Testing Yahoo Finance VIX fetch..."
VIX_PRICE=$(python3 -c "
import yfinance as yf
vix = yf.Ticker('^VIX')
try:
    hist = vix.history(period='5d')
    if not hist.empty:
        print(f'{hist[\"Close\"].iloc[-1]:.2f}')
    else:
        print('0')
except:
    print('0')
" 2>/dev/null)

if [ -n "$VIX_PRICE" ] && [ "$VIX_PRICE" != "0" ] && [ "$VIX_PRICE" != "18.00" ]; then
    echo "   VIX Price from Yahoo: $VIX_PRICE"
    check 0 "Yahoo VIX fetch returns real price"
else
    echo "   VIX Price: $VIX_PRICE (expected ~14-16)"
    check 1 "Yahoo VIX fetch returns real price"
fi

# -----------------------------------------------------------------------------
# 3. Test unified_data_provider
# -----------------------------------------------------------------------------
echo ""
echo "3. Testing unified_data_provider.get_vix()..."
UDP_VIX=$(python3 -c "
import sys
sys.path.insert(0, '.')
from data.unified_data_provider import UnifiedDataProvider
provider = UnifiedDataProvider()
vix = provider.get_vix()
print(f'{vix:.2f}')
" 2>/dev/null)

if [ -n "$UDP_VIX" ] && [ "$UDP_VIX" != "0.00" ] && [ "$UDP_VIX" != "18.00" ]; then
    echo "   VIX from unified_data_provider: $UDP_VIX"
    check 0 "unified_data_provider returns real VIX"
else
    echo "   VIX: $UDP_VIX (got fallback value)"
    check 1 "unified_data_provider returns real VIX"
fi

# -----------------------------------------------------------------------------
# 4. Test vix_hedge_manager
# -----------------------------------------------------------------------------
echo ""
echo "4. Testing vix_hedge_manager.get_vix_data()..."
VHM_RESULT=$(python3 -c "
import sys
sys.path.insert(0, '.')
from core.vix_hedge_manager import get_vix_hedge_manager
manager = get_vix_hedge_manager()
data = manager.get_vix_data()
print(f'{data.get(\"vix_spot\", 0):.2f}|{data.get(\"vix_source\", \"unknown\")}')
" 2>/dev/null)

VHM_VIX=$(echo "$VHM_RESULT" | cut -d'|' -f1)
VHM_SOURCE=$(echo "$VHM_RESULT" | cut -d'|' -f2)

if [ -n "$VHM_VIX" ] && [ "$VHM_VIX" != "0.00" ] && [ "$VHM_VIX" != "18.00" ]; then
    echo "   VIX: $VHM_VIX (source: $VHM_SOURCE)"
    check 0 "vix_hedge_manager returns real VIX"
else
    echo "   VIX: $VHM_VIX (source: $VHM_SOURCE)"
    warn "Got fallback value - check Tradier/Yahoo config"
    check 1 "vix_hedge_manager returns real VIX"
fi

# -----------------------------------------------------------------------------
# 5. Check API endpoint (if server is running)
# -----------------------------------------------------------------------------
echo ""
echo "5. Testing /api/vix/current endpoint..."
API_URL="${API_URL:-http://localhost:8000}"

API_RESULT=$(curl -s --max-time 5 "$API_URL/api/vix/current" 2>/dev/null || echo "")

if [ -n "$API_RESULT" ]; then
    API_VIX=$(echo "$API_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('vix_spot',0))" 2>/dev/null)
    API_SOURCE=$(echo "$API_RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('vix_source','unknown'))" 2>/dev/null)

    if [ -n "$API_VIX" ] && [ "$API_VIX" != "0" ] && [ "$API_VIX" != "18.0" ]; then
        echo "   VIX: $API_VIX (source: $API_SOURCE)"
        check 0 "API returns real VIX"
    else
        echo "   VIX: $API_VIX (source: $API_SOURCE)"
        check 1 "API returns real VIX"
    fi
else
    warn "API not reachable at $API_URL (server may not be running)"
    echo "   Skipping API test"
fi

# -----------------------------------------------------------------------------
# 6. Verify no hardcoded wrong defaults remain
# -----------------------------------------------------------------------------
echo ""
echo "6. Checking for incorrect default values..."

# Check for 0.0 returns in VIX code
ZERO_RETURNS=$(grep -r "return 0\.0" data/unified_data_provider.py 2>/dev/null | grep -i vix | wc -l)
if [ "$ZERO_RETURNS" -eq 0 ]; then
    check 0 "No 'return 0.0' in VIX code path"
else
    check 1 "Found 'return 0.0' in VIX code - should return 18.0"
fi

# Check unified default is 18.0
DEFAULT_18=$(grep -c "return 18.0" data/unified_data_provider.py 2>/dev/null || echo "0")
if [ "$DEFAULT_18" -gt 0 ]; then
    check 0 "unified_data_provider uses 18.0 fallback"
else
    check 1 "unified_data_provider should use 18.0 fallback"
fi

# -----------------------------------------------------------------------------
# 7. Verify Polygon removed from VIX sources
# -----------------------------------------------------------------------------
echo ""
echo "7. Checking Polygon removed from VIX sources..."

POLYGON_IN_SOURCES=$(grep -A5 "sources = \[" backend/api/routes/vix_routes.py 2>/dev/null | grep -c "polygon" || echo "0")
if [ "$POLYGON_IN_SOURCES" -eq 0 ]; then
    check 0 "Polygon removed from VIX sources in vix_routes.py"
else
    check 1 "Polygon still in VIX sources - should be removed"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  SUMMARY"
echo "=============================================="
echo ""
echo -e "  ${GREEN}Passed${NC}: $PASS"
echo -e "  ${RED}Failed${NC}: $FAIL"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All VIX fixes verified successfully!${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed. Review the output above.${NC}"
    echo ""
    echo "Common fixes:"
    echo "  1. Run: pip install yfinance"
    echo "  2. Restart the backend service"
    echo "  3. Check TRADIER_SANDBOX setting in environment"
    exit 1
fi
