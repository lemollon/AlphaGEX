#!/usr/bin/env python3
"""
Close All Tradier Sandbox Positions
====================================

Emergency script to close ALL open option positions across ALL three
Tradier sandbox accounts (User, Matt, Logan).

For each position it sends a market order to close. Options get
buy_to_close or sell_to_close depending on the current side.

Usage:
    # Dry run (default) — shows what WOULD be closed
    python ironforge/scripts/close_all_tradier_positions.py

    # Actually close everything
    python ironforge/scripts/close_all_tradier_positions.py --execute

    # Close only one account
    python ironforge/scripts/close_all_tradier_positions.py --execute --account User

    # Close only stock/equity positions (not options)
    python ironforge/scripts/close_all_tradier_positions.py --execute --equities-only
"""

import os
import sys
import time
import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional

# Add ironforge/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

CT = ZoneInfo("America/Chicago")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("close_all")


# ---------------------------------------------------------------------------
# Tradier API helpers (standalone — no dependency on trading.tradier_client)
# ---------------------------------------------------------------------------

SANDBOX_URL = "https://sandbox.tradier.com/v1"
PROD_URL = "https://api.tradier.com/v1"


def get_positions(base_url: str, api_key: str, account_id: str) -> List[Dict]:
    """Fetch all open positions from a Tradier account."""
    url = f"{base_url}/accounts/{account_id}/positions"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        positions = data.get("positions", {})
        if positions == "null" or not positions:
            return []
        pos_list = positions.get("position", [])
        if isinstance(pos_list, dict):
            return [pos_list]
        return pos_list if pos_list else []
    except Exception as e:
        log.error(f"Failed to fetch positions: {e}")
        return []


def close_position(
    base_url: str,
    api_key: str,
    account_id: str,
    symbol: str,
    qty: float,
    side: str,
    tag: str = "",
) -> Optional[Dict]:
    """
    Close a single position with a market order.

    Args:
        symbol: OCC option symbol (e.g. SPY260312P00580000) or stock ticker
        qty: absolute quantity to close
        side: "buy_to_close" or "sell_to_close" for options,
              "sell" for long stock, "buy_to_cover" for short stock
        tag: optional order tag
    """
    url = f"{base_url}/accounts/{account_id}/orders"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    # Determine if option or equity
    is_option = len(symbol) > 6  # OCC symbols are long

    if is_option:
        # Extract underlying from OCC symbol (first 1-5 chars before the date)
        # SPY260312P00580000 → SPY
        underlying = ""
        for i, c in enumerate(symbol):
            if c.isdigit():
                underlying = symbol[:i]
                break
        if not underlying:
            underlying = symbol[:3]

        order_data = {
            "class": "option",
            "symbol": underlying,
            "option_symbol": symbol,
            "side": side,
            "quantity": str(int(abs(qty))),
            "type": "market",
            "duration": "day",
        }
    else:
        order_data = {
            "class": "equity",
            "symbol": symbol,
            "side": side,
            "quantity": str(int(abs(qty))),
            "type": "market",
            "duration": "day",
        }

    if tag:
        order_data["tag"] = tag[:255]

    try:
        resp = requests.post(url, headers=headers, data=order_data, timeout=15)
        resp.raise_for_status()
        result = resp.json()
        order = result.get("order", {})
        return {
            "order_id": order.get("id"),
            "status": order.get("status", "unknown"),
        }
    except requests.exceptions.HTTPError as e:
        log.error(f"Order rejected for {symbol}: {e} — {e.response.text if e.response else ''}")
        return None
    except Exception as e:
        log.error(f"Order failed for {symbol}: {e}")
        return None


def get_account_balance(base_url: str, api_key: str, account_id: str) -> Optional[Dict]:
    """Fetch account balance summary."""
    url = f"{base_url}/accounts/{account_id}/balances"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("balances", {})
    except Exception as e:
        log.warning(f"Could not fetch balance: {e}")
        return None


# ---------------------------------------------------------------------------
# Account discovery
# ---------------------------------------------------------------------------

def get_all_accounts(account_filter: str = None) -> List[Dict]:
    """
    Build list of all Tradier sandbox accounts from env vars.
    Returns list of {"name": str, "api_key": str, "account_id": str, "base_url": str}
    """
    accounts = []

    # Primary account (TRADIER_API_KEY / TRADIER_ACCOUNT_ID)
    primary_key = os.getenv("TRADIER_API_KEY", "")
    primary_id = os.getenv("TRADIER_ACCOUNT_ID", "")
    primary_url = os.getenv("TRADIER_BASE_URL", SANDBOX_URL)
    if primary_key and primary_id:
        accounts.append({
            "name": "Primary",
            "api_key": primary_key,
            "account_id": primary_id,
            "base_url": primary_url,
        })

    # Three sandbox accounts for FLAME mirroring
    for label, env_key, env_id in [
        ("User", "TRADIER_SANDBOX_KEY_USER", "TRADIER_SANDBOX_ACCOUNT_ID_USER"),
        ("Matt", "TRADIER_SANDBOX_KEY_MATT", "TRADIER_SANDBOX_ACCOUNT_ID_MATT"),
        ("Logan", "TRADIER_SANDBOX_KEY_LOGAN", "TRADIER_SANDBOX_ACCOUNT_ID_LOGAN"),
    ]:
        key = os.getenv(env_key, "")
        acct_id = os.getenv(env_id, "")
        if key and acct_id:
            # Skip if same as primary (avoid duplicate)
            if acct_id == primary_id:
                continue
            accounts.append({
                "name": label,
                "api_key": key,
                "account_id": acct_id,
                "base_url": SANDBOX_URL,
            })

    if account_filter:
        accounts = [a for a in accounts if a["name"].lower() == account_filter.lower()]

    return accounts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Close all Tradier sandbox positions")
    parser.add_argument("--execute", action="store_true", help="Actually send close orders (default is dry run)")
    parser.add_argument("--account", type=str, default=None, help="Only close positions for this account name")
    parser.add_argument("--equities-only", action="store_true", help="Only close equity/stock positions")
    parser.add_argument("--options-only", action="store_true", help="Only close option positions")
    args = parser.parse_args()

    now = datetime.now(CT)
    mode = "EXECUTE" if args.execute else "DRY RUN"

    print("=" * 65)
    print(f"  Close All Tradier Positions — {mode}")
    print(f"  Time: {now.strftime('%Y-%m-%d %H:%M:%S CT')}")
    print("=" * 65)

    accounts = get_all_accounts(args.account)
    if not accounts:
        print("\n  No Tradier accounts found. Set environment variables:")
        print("    TRADIER_API_KEY + TRADIER_ACCOUNT_ID (primary)")
        print("    TRADIER_SANDBOX_KEY_USER + TRADIER_SANDBOX_ACCOUNT_ID_USER")
        print("    TRADIER_SANDBOX_KEY_MATT + TRADIER_SANDBOX_ACCOUNT_ID_MATT")
        print("    TRADIER_SANDBOX_KEY_LOGAN + TRADIER_SANDBOX_ACCOUNT_ID_LOGAN")
        sys.exit(1)

    print(f"\n  Found {len(accounts)} account(s): {', '.join(a['name'] for a in accounts)}")

    total_positions = 0
    total_closed = 0
    total_failed = 0
    total_skipped = 0

    for acct in accounts:
        name = acct["name"]
        base_url = acct["base_url"]
        api_key = acct["api_key"]
        account_id = acct["account_id"]
        is_sandbox = "sandbox" in base_url

        print(f"\n{'─' * 65}")
        print(f"  Account: {name} ({'SANDBOX' if is_sandbox else 'PRODUCTION'}) — {account_id}")
        print(f"{'─' * 65}")

        # Fetch balance
        balance = get_account_balance(base_url, api_key, account_id)
        if balance:
            equity = balance.get("total_equity", balance.get("equity", "?"))
            print(f"  Balance: equity=${equity}")

        # Fetch positions
        positions = get_positions(base_url, api_key, account_id)
        if not positions:
            print("  No open positions.")
            continue

        print(f"  {len(positions)} open position(s):\n")

        for pos in positions:
            symbol = pos.get("symbol", "???")
            qty = float(pos.get("quantity", 0))
            cost_basis = float(pos.get("cost_basis", 0))
            date_acquired = pos.get("date_acquired", "?")
            is_option = len(symbol) > 6

            # Filter by type
            if args.equities_only and is_option:
                total_skipped += 1
                continue
            if args.options_only and not is_option:
                total_skipped += 1
                continue

            total_positions += 1

            # Determine close side
            if is_option:
                # qty > 0 = long (bought) → sell_to_close
                # qty < 0 = short (sold) → buy_to_close
                if qty > 0:
                    side = "sell_to_close"
                    side_label = "SELL_TO_CLOSE"
                else:
                    side = "buy_to_close"
                    side_label = "BUY_TO_CLOSE"
            else:
                if qty > 0:
                    side = "sell"
                    side_label = "SELL"
                else:
                    side = "buy_to_cover"
                    side_label = "BUY_TO_COVER"

            abs_qty = int(abs(qty))
            print(f"    {symbol:30s}  qty={qty:>6.0f}  cost=${cost_basis:>10.2f}  acquired={date_acquired}")

            if not args.execute:
                print(f"      [DRY RUN] Would {side_label} {abs_qty} @ market")
                continue

            # Execute close
            tag = f"CLOSE_ALL_{now.strftime('%Y%m%d_%H%M')}"
            result = close_position(base_url, api_key, account_id, symbol, abs_qty, side, tag)

            if result and result.get("order_id"):
                total_closed += 1
                print(f"      CLOSED: order_id={result['order_id']} status={result['status']}")
            else:
                total_failed += 1
                print(f"      FAILED to close!")

            # Small delay between orders to avoid rate limiting
            time.sleep(0.3)

    # Summary
    print(f"\n{'=' * 65}")
    print(f"  SUMMARY")
    print(f"  Total positions found: {total_positions}")
    if args.execute:
        print(f"  Successfully closed:   {total_closed}")
        print(f"  Failed to close:       {total_failed}")
    else:
        print(f"  [DRY RUN] — no orders sent. Use --execute to close.")
    if total_skipped > 0:
        print(f"  Skipped (filtered):    {total_skipped}")
    print(f"{'=' * 65}")

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
