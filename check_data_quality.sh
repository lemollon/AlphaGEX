#!/bin/bash
###############################################################################
# Quick Data Quality Check
# Shows table population status and recommendations
###############################################################################

echo "================================================================================"
echo "⚡ QUICK DATA QUALITY CHECK"
echo "================================================================================"
echo ""

python3 data_quality_dashboard.py --quick

echo ""
echo "For full report, run: python3 data_quality_dashboard.py"
echo "For JSON output, run: python3 data_quality_dashboard.py --json"
echo ""
