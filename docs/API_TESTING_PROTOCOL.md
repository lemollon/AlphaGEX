# API Testing Protocol

## Critical Understanding

**The API keys ARE working. The issue is Claude's environment cannot access external APIs.**

## Evidence

The following APIs have been verified as working by the user:

### Trading Volatility API (Confirmed Working - 2025-11-14)
```json
SPY: {
  "collection_date": "2025-11-14 20:46:17",
  "price": "672.4",
  "gex_flip_price": "677.55",
  "skew_adjusted_gex": "-1017367026.884",
  "gex_per_1pct_chg": "-1017367026.884",
  "call_put_delta_spread": "-0.024952374162191926",
  "implied_volatility": "0.16065465569615178",
  "next_expiration": "2025-11-17",
  "nearest_gex_value": "-65968444.532",
  "put_call_ratio_open_interest": "1.82",
  "gamma_formation": "0",
  "average_volume": "82776138",
  "rating": "1"
}

QQQ: {
  "collection_date": "2025-11-14 20:48:06",
  "price": "608.75",
  "gex_flip_price": "615.81",
  "skew_adjusted_gex": "-684133344.8375",
  "gex_per_1pct_chg": "-684133344.8375",
  "call_put_delta_spread": "-0.0054848327946804",
  "implied_volatility": "0.22519667844446825",
  "next_expiration": "2025-11-17",
  "nearest_gex_value": "74182122.8125",
  "put_call_ratio_open_interest": "1.4",
  "gamma_formation": "0",
  "average_volume": "70849453",
  "rating": "1"
}
```

### Polygon API (Confirmed Working - 2025-11-14)
```json
{
  "ticker": "SPY",
  "queryCount": 1,
  "resultsCount": 1,
  "adjusted": true,
  "results": [{
    "T": "SPY",
    "v": 9.6823977e+07,
    "vw": 671.2901,
    "o": 665.38,
    "c": 671.93,
    "h": 675.66,
    "l": 663.265,
    "t": 1763154000000,
    "n": 1468233
  }],
  "status": "OK"
}
```

## New Protocol

### DO NOT
- ❌ Test API keys from Claude's environment
- ❌ Claim API keys are invalid without user verification
- ❌ Assume network errors mean bad credentials
- ❌ Try to validate APIs that Claude cannot access

### DO
- ✅ Ask the user to test API endpoints
- ✅ Provide test commands/URLs for the user to run
- ✅ Focus on data validation and error handling in the app
- ✅ Assume APIs work if user confirms they work
- ✅ Debug based on data structure mismatches, not API availability

## Troubleshooting Workflow

1. **User reports API issue** → Ask user to test the endpoint directly
2. **User confirms API works** → Focus on app's data handling, not API keys
3. **Debugging needed** → Look for:
   - Missing null checks
   - Data structure validation
   - Error handling gaps
   - Response serialization issues

## Real Issues to Focus On

Since APIs are confirmed working, the actual problems are:

1. **Data Validation** - Missing checks before accessing nested properties
2. **Error Handling** - Silent failures not reaching frontend
3. **Null Safety** - Accessing properties on potentially undefined objects
4. **Response Structure** - Assumptions about data format without validation

## Documentation Updated
2025-11-17
