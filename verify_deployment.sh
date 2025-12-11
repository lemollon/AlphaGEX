#!/bin/bash
# Deployment Verification Script
# Run during build to verify correct code is deployed

echo "=========================================="
echo "DEPLOYMENT VERIFICATION"
echo "=========================================="
echo ""
echo "📍 Current Directory: $(pwd)"
echo "📂 Directory Contents:"
ls -la | head -20
echo ""
echo "🔍 Git Information:"
echo "   Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'NOT A GIT REPO')"
echo "   Branch: $(git branch --show-current 2>/dev/null || echo 'DETACHED HEAD')"
echo "   Remote: $(git remote get-url origin 2>/dev/null || echo 'NO REMOTE')"
echo ""
echo "🔍 Checking db/config_and_database.py (line 7 should NOT have streamlit):"
echo "   Lines 5-10:"
sed -n '5,10p' db/config_and_database.py || echo "   [File not found - skipping check]"
echo ""
echo "🔍 Checking core/intelligence_and_strategies.py (lines 7-12 should have try/except):"
echo "   Lines 7-12:"
sed -n '7,12p' core/intelligence_and_strategies.py || echo "   [File not found - skipping check]"
echo ""
echo "=========================================="
echo "END VERIFICATION"
echo "=========================================="
