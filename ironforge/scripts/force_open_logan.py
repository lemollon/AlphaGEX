#!/usr/bin/env python3
"""
Force-Open Iron Condor for Logan's Sandbox
===========================================

Mirrors an existing FLAME position into Logan's Tradier sandbox account.
The paper position already exists in Databricks; this script only places
the sandbox order and prints the SQL to update the position record.

Usage:
    python force_open_logan.py

    # Or override position details via env vars:
    POSITION_ID=FLAME-20260303-CF57C python force_open_logan.py

Requirements: requests  (pip install requests)
"""

import json
import math
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

# ── Logan's sandbox credentials ──────────────────────────────────────
LOGAN_API_KEY = "AcDucIMyjeNgFh60LWOb0F5fhXHh"
LOGAN_ACCOUNT_ID = "VA59240884"
SANDBOX_URL = "https://sandbox.tradier.com/v1"

# ── Position details (from FLAME-20260303-CF57C) ─────────────────────
POSITION_ID = "FLAME-20260303-CF57C"
TICKER = "SPY"
EXPIRATION = "2026-03-05"
PUT_SHORT_STRIKE = 662
PUT_LONG_STRIKE = 657
CALL_SHORT_STRIKE = 689
CALL_LONG_STRIKE = 694
ENTRY_CREDIT = 1.08
SPREAD_WIDTH = 5  # $5 wings

HEADERS = {
    "Authorization": f"Bearer {LOGAN_API_KEY}",
    "Accept": "application/json",
}


def build_occ(ticker: str, expiration: str, strike: int, option_type: str) -> str:
    """Build OCC option symbol: SPY260305P00662000."""
    parts = expiration.split("-")
    yy, mm, dd = parts[0][2:], parts[1], parts[2]
    strike_part = str(strike * 1000).zfill(8)
    return f"{ticker}{yy}{mm}{dd}{option_type}{strike_part}"


def main():
    print("=" * 60)
    print(f"  FORCE-OPEN IRON CONDOR: Logan's Sandbox")
    print(f"  Position: {POSITION_ID}")
    print(f"  Strikes: {PUT_LONG_STRIKE}/{PUT_SHORT_STRIKE}P - "
          f"{CALL_SHORT_STRIKE}/{CALL_LONG_STRIKE}C")
    print(f"  Expiration: {EXPIRATION}")
    print("=" * 60)

    # ── Step 1: Get Logan's buying power ─────────────────────────────
    print(f"\n{'─' * 56}")
    print("  STEP 1: GET LOGAN'S BUYING POWER")
    print(f"{'─' * 56}")

    resp = requests.get(
        f"{SANDBOX_URL}/accounts/{LOGAN_ACCOUNT_ID}/balances",
        headers=HEADERS,
        timeout=15,
    )
    if not resp.ok:
        print(f"  ERROR: Balances request failed: {resp.status_code} {resp.text}")
        sys.exit(1)

    balances = resp.json()
    bal = balances.get("balances", {})
    buying_power = float(bal.get("option_buying_power") or bal.get("buying_power") or 0)
    cash = float(bal.get("cash", {}).get("cash_available", 0) if isinstance(bal.get("cash"), dict) else bal.get("total_cash", 0))

    print(f"  Option Buying Power: ${buying_power:,.2f}")
    print(f"  Cash:                ${cash:,.2f}")
    print(f"  Full response: {json.dumps(bal, indent=2)[:500]}")

    if buying_power <= 0:
        # Fallback: try total_equity or total_cash
        buying_power = float(bal.get("total_equity", 0) or bal.get("total_cash", 0))
        print(f"  Fallback buying power: ${buying_power:,.2f}")

    if buying_power <= 0:
        print("  ERROR: Cannot determine buying power")
        sys.exit(1)

    # ── Step 2: Calculate Logan's contract count ─────────────────────
    print(f"\n{'─' * 56}")
    print("  STEP 2: CALCULATE CONTRACTS")
    print(f"{'─' * 56}")

    collateral_per = (SPREAD_WIDTH - ENTRY_CREDIT) * 100
    usable_bp = buying_power * 0.85
    logan_contracts = math.floor(usable_bp / collateral_per)

    print(f"  Spread width:          ${SPREAD_WIDTH}")
    print(f"  Entry credit:          ${ENTRY_CREDIT}")
    print(f"  Collateral/contract:   ${collateral_per:.2f}")
    print(f"  Usable BP (85%):       ${usable_bp:,.2f}")
    print(f"  Logan contracts:       {logan_contracts}")

    if logan_contracts < 1:
        print("  ERROR: Cannot afford any contracts")
        sys.exit(1)

    # ── Step 3: Place 4-leg multileg order ───────────────────────────
    print(f"\n{'─' * 56}")
    print("  STEP 3: PLACE 4-LEG ORDER")
    print(f"{'─' * 56}")

    put_short_occ = build_occ(TICKER, EXPIRATION, PUT_SHORT_STRIKE, "P")
    put_long_occ = build_occ(TICKER, EXPIRATION, PUT_LONG_STRIKE, "P")
    call_short_occ = build_occ(TICKER, EXPIRATION, CALL_SHORT_STRIKE, "C")
    call_long_occ = build_occ(TICKER, EXPIRATION, CALL_LONG_STRIKE, "C")

    print(f"  Put  short (sell): {put_short_occ}")
    print(f"  Put  long  (buy):  {put_long_occ}")
    print(f"  Call short (sell): {call_short_occ}")
    print(f"  Call long  (buy):  {call_long_occ}")
    print(f"  Contracts:         {logan_contracts}")

    order_body = {
        "class": "multileg",
        "symbol": TICKER,
        "type": "market",
        "duration": "day",
        "option_symbol[0]": put_short_occ,
        "side[0]": "sell_to_open",
        "quantity[0]": str(logan_contracts),
        "option_symbol[1]": put_long_occ,
        "side[1]": "buy_to_open",
        "quantity[1]": str(logan_contracts),
        "option_symbol[2]": call_short_occ,
        "side[2]": "sell_to_open",
        "quantity[2]": str(logan_contracts),
        "option_symbol[3]": call_long_occ,
        "side[3]": "buy_to_open",
        "quantity[3]": str(logan_contracts),
        "tag": POSITION_ID[:255],
    }

    print(f"\n  Sending order...")
    resp = requests.post(
        f"{SANDBOX_URL}/accounts/{LOGAN_ACCOUNT_ID}/orders",
        headers={
            **HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=order_body,
        timeout=15,
    )

    if not resp.ok:
        print(f"  ERROR: Order failed: {resp.status_code}")
        print(f"  Response: {resp.text}")
        sys.exit(1)

    order_result = resp.json()
    order_id = order_result.get("order", {}).get("id")

    if not order_id:
        print(f"  ERROR: No order ID in response: {json.dumps(order_result, indent=2)}")
        sys.exit(1)

    print(f"  ORDER PLACED!")
    print(f"  Order ID: {order_id}")
    print(f"  Response: {json.dumps(order_result, indent=2)}")

    # ── Step 4: Print Databricks UPDATE SQL ──────────────────────────
    print(f"\n{'─' * 56}")
    print("  STEP 4: DATABRICKS UPDATE SQL")
    print(f"{'─' * 56}")

    # First, we need the current sandbox_order_id JSON to merge Logan's entry.
    # The current value should have User and Matt entries already.
    # We add Logan's entry.
    logan_entry = {"Logan": {"order_id": order_id, "contracts": logan_contracts}}

    print(f"\n  Logan's entry: {json.dumps(logan_entry)}")
    print(f"\n  ──── Run this in Databricks SQL editor ────")
    print(f"""
  -- First, check current value:
  SELECT position_id, sandbox_order_id
  FROM alpha_prime.ironforge.flame_positions
  WHERE position_id = '{POSITION_ID}';

  -- Then update (merge Logan into existing JSON):
  -- If current sandbox_order_id is empty or NULL:
  UPDATE alpha_prime.ironforge.flame_positions
  SET sandbox_order_id = '{json.dumps(logan_entry)}'
  WHERE position_id = '{POSITION_ID}'
    AND (sandbox_order_id IS NULL OR sandbox_order_id = '');

  -- If current sandbox_order_id already has User/Matt entries,
  -- copy the existing JSON and add Logan's entry.
  -- Example: if current value is {{"User": {{"order_id": 111, "contracts": 85}}, "Matt": {{"order_id": 222, "contracts": 50}}}}
  -- Then set it to:
  -- {{"User": {{"order_id": 111, "contracts": 85}}, "Matt": {{"order_id": 222, "contracts": 50}}, "Logan": {{"order_id": {order_id}, "contracts": {logan_contracts}}}}}
""")

    # ── Step 5: Verify positions ─────────────────────────────────────
    print(f"{'─' * 56}")
    print("  STEP 5: VERIFY LOGAN'S POSITIONS")
    print(f"{'─' * 56}")

    time.sleep(2)  # Brief pause for order to settle

    resp = requests.get(
        f"{SANDBOX_URL}/accounts/{LOGAN_ACCOUNT_ID}/positions",
        headers=HEADERS,
        timeout=15,
    )

    if resp.ok:
        positions = resp.json()
        print(f"  Positions response: {json.dumps(positions, indent=2)[:1000]}")
    else:
        print(f"  WARNING: Could not verify positions: {resp.status_code}")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Logan's buying power:  ${buying_power:,.2f}")
    print(f"  Contracts placed:      {logan_contracts}")
    print(f"  Order ID:              {order_id}")
    print(f"  Collateral used:       ${collateral_per * logan_contracts:,.2f}")
    print(f"  Max profit:            ${ENTRY_CREDIT * 100 * logan_contracts:,.2f}")
    print(f"  Max loss:              ${collateral_per * logan_contracts:,.2f}")
    print(f"")
    print(f"  REMAINING ACTION:")
    print(f"  1. Run the Databricks SQL above to update sandbox_order_id")
    print(f"  2. Verify on the dashboard that Logan appears in the position")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
