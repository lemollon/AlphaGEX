#!/bin/bash
echo "=========================================="
echo "JUBILEE IC POST-FIX VALIDATION"
echo "$(date)"
echo "=========================================="

cd "$(dirname "$0")"

for script in test_01*.py test_02*.py test_03*.py test_04*.py test_05*.py test_06*.py test_07*.py test_08*.py test_09*.py test_10*.py test_11*.py; do
    echo ""
    echo "--- Running $script ---"
    python3 "$script"
    echo "--- Done ---"
done

echo ""
echo "=========================================="
echo "ALL TESTS COMPLETE"
echo "=========================================="
