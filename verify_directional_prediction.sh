#!/bin/bash
# Comprehensive verification script for directional prediction feature

echo "======================================================================="
echo "🔍 DIRECTIONAL PREDICTION FEATURE - VERIFICATION"
echo "======================================================================="
echo ""

ISSUES_FOUND=0

# Test 1: Check if code exists
echo "Test 1: Checking if directional prediction code exists..."
if grep -q "SPY DIRECTIONAL FORECAST" gex_copilot.py; then
    echo "   ✅ PASS - Code found in gex_copilot.py"
    LINE_NUM=$(grep -n "SPY DIRECTIONAL FORECAST" gex_copilot.py | head -1 | cut -d: -f1)
    echo "      Location: Line $LINE_NUM"
else
    echo "   ❌ FAIL - Code NOT found!"
    echo "      Action: Run 'git pull origin $(git branch --show-current)'"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi
echo ""

# Test 2: Check syntax
echo "Test 2: Checking Python syntax..."
if python3 -m py_compile gex_copilot.py 2>/dev/null; then
    echo "   ✅ PASS - No syntax errors"
else
    echo "   ❌ FAIL - Syntax errors found!"
    python3 -m py_compile gex_copilot.py
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi
echo ""

# Test 3: Check git status
echo "Test 3: Checking git status..."
CURRENT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "   Current commit: $CURRENT_COMMIT"
echo "   Current branch: $CURRENT_BRANCH"

# Check if commit 47cf79a is in history
if git log --oneline | grep -q "47cf79a"; then
    echo "   ✅ PASS - Commit 47cf79a (directional prediction) found in history"
else
    echo "   ⚠️  WARNING - Commit 47cf79a not in history"
    echo "      You may need to pull the latest code"
fi
echo ""

# Test 4: Check if prediction logic is complete
echo "Test 4: Checking if all prediction components exist..."
COMPONENTS=(
    "bullish_score"
    "confidence_factors"
    "direction_emoji"
    "SPY DIRECTIONAL FORECAST"
    "Expected Move:"
)

ALL_FOUND=true
for component in "${COMPONENTS[@]}"; do
    if grep -q "$component" gex_copilot.py; then
        echo "   ✅ Found: $component"
    else
        echo "   ❌ Missing: $component"
        ALL_FOUND=false
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done

if [ "$ALL_FOUND" = true ]; then
    echo "   ✅ PASS - All components present"
else
    echo "   ❌ FAIL - Some components missing"
fi
echo ""

# Test 5: Run logic test
echo "Test 5: Testing prediction logic..."
if [ -f "test_directional_prediction.py" ]; then
    if python3 test_directional_prediction.py > /tmp/prediction_test.log 2>&1; then
        echo "   ✅ PASS - Logic test successful"
        # Show the prediction result
        grep "Direction:" /tmp/prediction_test.log | head -1
        grep "Probability:" /tmp/prediction_test.log | head -1
    else
        echo "   ❌ FAIL - Logic test failed"
        cat /tmp/prediction_test.log
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
else
    echo "   ⚠️  SKIP - test_directional_prediction.py not found"
fi
echo ""

# Test 6: Check for Python cache that might have old code
echo "Test 6: Checking for stale Python cache..."
CACHE_COUNT=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)
if [ "$CACHE_COUNT" -gt 0 ]; then
    echo "   ⚠️  WARNING - Found $CACHE_COUNT __pycache__ directories"
    echo "      These may contain old code. Run: find . -type d -name '__pycache__' -exec rm -rf {} +"
else
    echo "   ✅ PASS - No cache directories found"
fi
echo ""

# Test 7: Check dependencies
echo "Test 7: Checking required dependencies..."
DEPS=("streamlit" "pandas" "yfinance")
for dep in "${DEPS[@]}"; do
    if python3 -c "import $dep" 2>/dev/null; then
        echo "   ✅ $dep installed"
    else
        echo "   ❌ $dep NOT installed"
        ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
done
echo ""

# Summary
echo "======================================================================="
echo "📊 VERIFICATION SUMMARY"
echo "======================================================================="
echo ""

if [ $ISSUES_FOUND -eq 0 ]; then
    echo "✅ ALL TESTS PASSED!"
    echo ""
    echo "The directional prediction feature is ready to use."
    echo ""
    echo "If you still don't see it on your website:"
    echo ""
    echo "1. 🔄 RESTART STREAMLIT APP:"
    echo "   Local: Stop the app (Ctrl+C) and run: streamlit run gex_copilot.py"
    echo "   Cloud: Reboot your app from the Streamlit Cloud dashboard"
    echo "   Server: ./restart_streamlit.sh"
    echo ""
    echo "2. 🧹 CLEAR BROWSER CACHE:"
    echo "   Press Ctrl+Shift+R (or Cmd+Shift+R on Mac)"
    echo ""
    echo "3. 🔍 CHECK LOCATION:"
    echo "   Navigate to: GEX Analysis → Gamma Expiration Intelligence"
    echo "   Look for large colored box above 'VIEW 1: TODAY'S IMPACT'"
    echo ""
    echo "4. 🔄 REFRESH DATA:"
    echo "   Click the '🔄 Refresh' button in the Gamma Intelligence section"
    echo ""
else
    echo "❌ FOUND $ISSUES_FOUND ISSUE(S)"
    echo ""
    echo "Please fix the issues above, then run this script again."
    echo ""
fi

echo "======================================================================="
echo ""
echo "For detailed troubleshooting, see:"
echo "  DIRECTIONAL_PREDICTION_TROUBLESHOOTING.md"
echo ""
