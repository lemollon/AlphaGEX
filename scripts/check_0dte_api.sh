#!/bin/bash
# Check the 0DTE comparison API response to debug field names

BACKEND_URL="${1:-https://your-backend-url.onrender.com}"

echo "Fetching 0DTE comparison data from: $BACKEND_URL/api/gex/compare/0dte/SPY"
echo "=========================================="

curl -s "$BACKEND_URL/api/gex/compare/0dte/SPY" | python3 -c "
import sys, json
data = json.load(sys.stdin)

print('\n=== TRADING VOLATILITY DEBUG INFO ===')
tv = data.get('trading_volatility', {})
debug = tv.get('_debug', {})

if debug:
    print(f'Raw field names: {debug.get(\"raw_fields\", \"N/A\")}')
    print(f'Sample strike data:')
    for k, v in debug.get('sample_strike', {}).items():
        print(f'  {k}: {v}')
else:
    print('No debug info found - API may not have returned data')
    print(f'Errors: {data.get(\"errors\", [])}')

print(f'\nStrikes count: {tv.get(\"strikes_count\", 0)}')
print(f'Net GEX: {tv.get(\"net_gex\", 0)}')
print(f'Spot: {tv.get(\"spot_price\", 0)}')

# Show first gamma array entry
gamma_arr = tv.get('gamma_array', [])
if gamma_arr:
    print(f'\nFirst strike in processed gamma_array:')
    print(f'  {gamma_arr[0]}')

print('\n=== TRADIER CALCULATED ===')
tr = data.get('tradier_calculated', {})
print(f'Strikes count: {tr.get(\"strikes_count\", 0)}')
print(f'Net GEX: {tr.get(\"net_gex\", 0)}')
tr_gamma = tr.get('gamma_array', [])
if tr_gamma:
    print(f'First strike: {tr_gamma[0]}')
"
