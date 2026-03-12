#!/usr/bin/env python3
"""
Close All Tradier Sandbox Positions (Iron Condor Multileg)
==========================================================

Emergency script to close ALL open option positions across ALL three
Tradier sandbox accounts (User, Matt, Logan).

Positions are grouped into Iron Condors by expiration and contract count,
then closed using the same cascade fallback as the live scanner:

    1. Try 4-leg multileg close (buy_to_close shorts, sell_to_close longs)
    2. If rejected -> try 2x2-leg spread closes (put spread + call spread)
    3. If rejected -> try 4 individual leg closes

Any legs that don't group into a clean IC are closed individually.

Usage:
    # Dry run (default) — shows what WOULD be closed
    python ironforge/scripts/close_all_tradier_positions.py

    # Actually close everything
    python ironforge/scripts/close_all_tradier_positions.py --execute

    # Close only one account
    python ironforge/scripts/close_all_tradier_positions.py --execute --account User
"""

import os
import re
import sys
import time
import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

import requests

CT = ZoneInfo("America/Chicago")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("close_all")

SANDBOX_URL = "https://sandbox.tradier.com/v1"

# OCC symbol regex: SPY260312P00580000
#   group 1 = underlying (e.g. SPY)
#   group 2 = date YYMMDD
#   group 3 = type P or C
#   group 4 = strike x1000 (e.g. 00580000 = 580.0)
OCC_RE = re.compile(r"^([A-Z]{1,6})(\d{6})([PC])(\d{8})$")


# ---------------------------------------------------------------------------
# OCC parsing
# ---------------------------------------------------------------------------

def parse_occ(symbol: str) -> Optional[Dict]:
    """Parse an OCC option symbol into its components."""
    m = OCC_RE.match(symbol)
    if not m:
        return None
    underlying, date_str, opt_type, strike_str = m.groups()
    strike = int(strike_str) / 1000.0
    expiration = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:6]}"
    return {
        "underlying": underlying,
        "expiration": expiration,
        "type": opt_type,  # P or C
        "strike": strike,
        "occ": symbol,
    }


# ---------------------------------------------------------------------------
# Tradier API helpers
# ---------------------------------------------------------------------------

def api_get(base_url: str, api_key: str, endpoint: str, params: Dict = None) -> Optional[Dict]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        resp = requests.get(f"{base_url}{endpoint}", headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"GET {endpoint} failed: {e}")
        return None


def api_post(base_url: str, api_key: str, endpoint: str, data: Dict = None) -> Optional[Dict]:
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    try:
        resp = requests.post(f"{base_url}{endpoint}", headers=headers, data=data, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        body = e.response.text if e.response else ""
        log.error(f"POST {endpoint} rejected: {e} — {body}")
        return None
    except Exception as e:
        log.error(f"POST {endpoint} failed: {e}")
        return None


def get_positions(base_url: str, api_key: str, account_id: str) -> List[Dict]:
    """Fetch all open positions from a Tradier account."""
    data = api_get(base_url, api_key, f"/accounts/{account_id}/positions")
    if not data:
        return []
    positions = data.get("positions", {})
    if positions == "null" or not positions:
        return []
    pos_list = positions.get("position", [])
    if isinstance(pos_list, dict):
        return [pos_list]
    return pos_list if pos_list else []


def get_balance(base_url: str, api_key: str, account_id: str) -> Optional[Dict]:
    data = api_get(base_url, api_key, f"/accounts/{account_id}/balances")
    return data.get("balances", {}) if data else None


# ---------------------------------------------------------------------------
# Iron Condor grouping
# ---------------------------------------------------------------------------

def group_into_iron_condors(positions: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    Group raw Tradier positions into Iron Condors.

    An IC has 4 legs on the same underlying + expiration with the same abs(qty):
        - 1 short put  (qty < 0, type P)
        - 1 long put   (qty > 0, type P)
        - 1 short call (qty < 0, type C)
        - 1 long call  (qty > 0, type C)

    Returns:
        (iron_condors, ungrouped_legs)
        iron_condors: list of dicts with IC details
        ungrouped_legs: positions that didn't fit into any IC
    """
    # Parse each position
    parsed = []
    non_options = []
    for pos in positions:
        symbol = pos.get("symbol", "")
        qty = float(pos.get("quantity", 0))
        info = parse_occ(symbol)
        if info:
            info["qty"] = qty
            info["raw"] = pos
            parsed.append(info)
        else:
            non_options.append(pos)

    # Group by (underlying, expiration, abs_qty)
    groups = defaultdict(list)
    for p in parsed:
        key = (p["underlying"], p["expiration"], int(abs(p["qty"])))
        groups[key].append(p)

    iron_condors = []
    used = set()

    for (underlying, expiration, contracts), legs in groups.items():
        short_puts = [l for l in legs if l["type"] == "P" and l["qty"] < 0]
        long_puts = [l for l in legs if l["type"] == "P" and l["qty"] > 0]
        short_calls = [l for l in legs if l["type"] == "C" and l["qty"] < 0]
        long_calls = [l for l in legs if l["type"] == "C" and l["qty"] > 0]

        # Match ICs: pair up one of each type
        while short_puts and long_puts and short_calls and long_calls:
            sp = short_puts.pop(0)
            lp = long_puts.pop(0)
            sc = short_calls.pop(0)
            lc = long_calls.pop(0)

            # Validate: long put < short put < short call < long call
            if not (lp["strike"] < sp["strike"] < sc["strike"] < lc["strike"]):
                # Try sorting by strike to find the right arrangement
                puts_sorted = sorted([sp, lp], key=lambda x: x["strike"])
                calls_sorted = sorted([sc, lc], key=lambda x: x["strike"])
                lp, sp = puts_sorted[0], puts_sorted[1]
                sc, lc = calls_sorted[0], calls_sorted[1]

            ic = {
                "underlying": underlying,
                "expiration": expiration,
                "contracts": contracts,
                "put_long": lp["strike"],
                "put_short": sp["strike"],
                "call_short": sc["strike"],
                "call_long": lc["strike"],
                "put_long_occ": lp["occ"],
                "put_short_occ": sp["occ"],
                "call_short_occ": sc["occ"],
                "call_long_occ": lc["occ"],
            }
            iron_condors.append(ic)
            used.update([id(sp["raw"]), id(lp["raw"]), id(sc["raw"]), id(lc["raw"])])

    # Anything not grouped is ungrouped
    ungrouped = []
    for p in parsed:
        if id(p["raw"]) not in used:
            ungrouped.append(p["raw"])
    ungrouped.extend(non_options)

    return iron_condors, ungrouped


# ---------------------------------------------------------------------------
# Close an IC with cascade fallback (4-leg -> 2x2-leg -> individual)
# ---------------------------------------------------------------------------

def close_ic_multileg(
    base_url: str,
    api_key: str,
    account_id: str,
    ic: Dict,
    tag: str = "",
) -> Dict:
    """
    Close an Iron Condor using the same cascade as the live scanner.

    Returns {"method": str, "success": bool, "details": str}
    """
    contracts = str(ic["contracts"])
    ticker = ic["underlying"]

    # ── Attempt 1: 4-leg multileg close ──
    order_data = {
        "class": "multileg",
        "symbol": ticker,
        "type": "market",
        "duration": "day",
        "option_symbol[0]": ic["put_short_occ"],
        "side[0]": "buy_to_close",
        "quantity[0]": contracts,
        "option_symbol[1]": ic["put_long_occ"],
        "side[1]": "sell_to_close",
        "quantity[1]": contracts,
        "option_symbol[2]": ic["call_short_occ"],
        "side[2]": "buy_to_close",
        "quantity[2]": contracts,
        "option_symbol[3]": ic["call_long_occ"],
        "side[3]": "sell_to_close",
        "quantity[3]": contracts,
    }
    if tag:
        order_data["tag"] = tag[:255]

    result = api_post(base_url, api_key, f"/accounts/{account_id}/orders", data=order_data)
    if result:
        order = result.get("order", {})
        oid = order.get("id")
        status = order.get("status", "unknown")
        if oid and status not in ("rejected", "error"):
            return {"method": "4-leg", "success": True, "details": f"order_id={oid} [{status}]"}
        log.warning(f"4-leg rejected ({status}), trying 2x2-leg")

    # ── Attempt 2: 2x2-leg spread closes ──
    put_data = {
        "class": "multileg",
        "symbol": ticker,
        "type": "market",
        "duration": "day",
        "option_symbol[0]": ic["put_short_occ"],
        "side[0]": "buy_to_close",
        "quantity[0]": contracts,
        "option_symbol[1]": ic["put_long_occ"],
        "side[1]": "sell_to_close",
        "quantity[1]": contracts,
    }
    if tag:
        put_data["tag"] = f"{tag}-PUT"[:255]

    call_data = {
        "class": "multileg",
        "symbol": ticker,
        "type": "market",
        "duration": "day",
        "option_symbol[0]": ic["call_short_occ"],
        "side[0]": "buy_to_close",
        "quantity[0]": contracts,
        "option_symbol[1]": ic["call_long_occ"],
        "side[1]": "sell_to_close",
        "quantity[1]": contracts,
    }
    if tag:
        call_data["tag"] = f"{tag}-CALL"[:255]

    put_result = api_post(base_url, api_key, f"/accounts/{account_id}/orders", data=put_data)
    call_result = api_post(base_url, api_key, f"/accounts/{account_id}/orders", data=call_data)

    put_ok = False
    call_ok = False
    if put_result:
        o = put_result.get("order", {})
        put_ok = o.get("id") and o.get("status") not in ("rejected", "error")
    if call_result:
        o = call_result.get("order", {})
        call_ok = o.get("id") and o.get("status") not in ("rejected", "error")

    if put_ok and call_ok:
        pid = put_result["order"]["id"]
        cid = call_result["order"]["id"]
        return {"method": "2x2-leg", "success": True, "details": f"put_order={pid} call_order={cid}"}

    if put_ok or call_ok:
        log.warning(f"2x2-leg partial (put={'OK' if put_ok else 'FAIL'} call={'OK' if call_ok else 'FAIL'}), closing remaining legs individually")

    # ── Attempt 3: individual leg closes ──
    leg_results = []
    legs = [
        (ic["put_short_occ"], "buy_to_close", "PS"),
        (ic["put_long_occ"], "sell_to_close", "PL"),
        (ic["call_short_occ"], "buy_to_close", "CS"),
        (ic["call_long_occ"], "sell_to_close", "CL"),
    ]

    # Skip legs that already closed in attempt 2
    if put_ok:
        legs = [l for l in legs if l[2] not in ("PS", "PL")]
    if call_ok:
        legs = [l for l in legs if l[2] not in ("CS", "CL")]

    for occ, side, label in legs:
        leg_data = {
            "class": "option",
            "symbol": ticker,
            "option_symbol": occ,
            "side": side,
            "quantity": contracts,
            "type": "market",
            "duration": "day",
        }
        if tag:
            leg_data["tag"] = f"{tag}-{label}"[:255]

        leg_result = api_post(base_url, api_key, f"/accounts/{account_id}/orders", data=leg_data)
        if leg_result:
            o = leg_result.get("order", {})
            if o.get("id") and o.get("status") not in ("rejected", "error"):
                leg_results.append(f"{label}={o['id']}")
            else:
                leg_results.append(f"{label}=REJECTED")
        else:
            leg_results.append(f"{label}=FAILED")
        time.sleep(0.2)

    all_ok = all("REJECTED" not in r and "FAILED" not in r for r in leg_results)
    partial = any("REJECTED" not in r and "FAILED" not in r for r in leg_results)

    method_parts = []
    if put_ok:
        method_parts.append("put_spread")
    if call_ok:
        method_parts.append("call_spread")
    if leg_results:
        method_parts.append("individual")
    method = "+".join(method_parts) if method_parts else "individual"

    if all_ok or (put_ok and call_ok):
        return {"method": method, "success": True, "details": " ".join(leg_results)}
    elif partial or put_ok or call_ok:
        return {"method": method, "success": True, "details": f"PARTIAL: {' '.join(leg_results)}"}
    else:
        return {"method": "all_failed", "success": False, "details": " ".join(leg_results)}


def close_single_leg(
    base_url: str,
    api_key: str,
    account_id: str,
    pos: Dict,
    tag: str = "",
) -> Optional[Dict]:
    """Close a single ungrouped position (option or equity)."""
    symbol = pos.get("symbol", "")
    qty = float(pos.get("quantity", 0))
    is_option = OCC_RE.match(symbol) is not None

    if is_option:
        info = parse_occ(symbol)
        underlying = info["underlying"] if info else symbol[:3]
        side = "sell_to_close" if qty > 0 else "buy_to_close"
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
        side = "sell" if qty > 0 else "buy_to_cover"
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

    result = api_post(base_url, api_key, f"/accounts/{account_id}/orders", data=order_data)
    if result:
        order = result.get("order", {})
        return {"order_id": order.get("id"), "status": order.get("status", "unknown")}
    return None


# ---------------------------------------------------------------------------
# Account discovery
# ---------------------------------------------------------------------------

def get_all_accounts(account_filter: str = None) -> List[Dict]:
    accounts = []

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

    for label, env_key, env_id in [
        ("User", "TRADIER_SANDBOX_KEY_USER", "TRADIER_SANDBOX_ACCOUNT_ID_USER"),
        ("Matt", "TRADIER_SANDBOX_KEY_MATT", "TRADIER_SANDBOX_ACCOUNT_ID_MATT"),
        ("Logan", "TRADIER_SANDBOX_KEY_LOGAN", "TRADIER_SANDBOX_ACCOUNT_ID_LOGAN"),
    ]:
        key = os.getenv(env_key, "")
        acct_id = os.getenv(env_id, "")
        if key and acct_id:
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
    parser = argparse.ArgumentParser(
        description="Close all Tradier sandbox positions as Iron Condors (multileg)"
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually send close orders (default is dry run)",
    )
    parser.add_argument(
        "--account", type=str, default=None,
        help="Only close positions for this account name (User, Matt, Logan, Primary)",
    )
    args = parser.parse_args()

    now = datetime.now(CT)
    mode = "EXECUTE" if args.execute else "DRY RUN"

    print("=" * 70)
    print(f"  Close All Tradier Positions (IC Multileg) — {mode}")
    print(f"  Time: {now.strftime('%Y-%m-%d %H:%M:%S CT')}")
    print(f"  Cascade: 4-leg -> 2x2-leg -> individual legs")
    print("=" * 70)

    accounts = get_all_accounts(args.account)
    if not accounts:
        print("\n  No Tradier accounts found. Set environment variables:")
        print("    TRADIER_API_KEY + TRADIER_ACCOUNT_ID (primary)")
        print("    TRADIER_SANDBOX_KEY_USER + TRADIER_SANDBOX_ACCOUNT_ID_USER")
        print("    TRADIER_SANDBOX_KEY_MATT + TRADIER_SANDBOX_ACCOUNT_ID_MATT")
        print("    TRADIER_SANDBOX_KEY_LOGAN + TRADIER_SANDBOX_ACCOUNT_ID_LOGAN")
        sys.exit(1)

    print(f"\n  Found {len(accounts)} account(s): {', '.join(a['name'] for a in accounts)}")

    total_ics = 0
    total_ungrouped = 0
    total_closed = 0
    total_failed = 0

    for acct in accounts:
        name = acct["name"]
        base_url = acct["base_url"]
        api_key = acct["api_key"]
        account_id = acct["account_id"]
        is_sandbox = "sandbox" in base_url

        print(f"\n{'─' * 70}")
        print(f"  Account: {name} ({'SANDBOX' if is_sandbox else 'PRODUCTION'}) — {account_id}")
        print(f"{'─' * 70}")

        # Fetch balance
        balance = get_balance(base_url, api_key, account_id)
        if balance:
            equity = balance.get("total_equity", balance.get("equity", "?"))
            print(f"  Equity: ${equity}")

        # Fetch positions
        positions = get_positions(base_url, api_key, account_id)
        if not positions:
            print("  No open positions.")
            continue

        print(f"  {len(positions)} raw position leg(s)")

        # Group into ICs
        ics, ungrouped = group_into_iron_condors(positions)
        total_ics += len(ics)
        total_ungrouped += len(ungrouped)

        # Display ICs
        if ics:
            print(f"\n  Iron Condors ({len(ics)}):")
            for i, ic in enumerate(ics, 1):
                print(
                    f"    IC #{i}: {ic['underlying']} {ic['expiration']}  "
                    f"{ic['put_long']}/{ic['put_short']}P — "
                    f"{ic['call_short']}/{ic['call_long']}C  "
                    f"x{ic['contracts']}"
                )

                if not args.execute:
                    print(f"           [DRY RUN] Would close as 4-leg multileg @ market")
                    continue

                # Close IC with cascade
                tag = f"CLOSE_ALL_{now.strftime('%Y%m%d_%H%M')}"
                result = close_ic_multileg(base_url, api_key, account_id, ic, tag)

                if result["success"]:
                    total_closed += 1
                    print(f"           CLOSED [{result['method']}]: {result['details']}")
                else:
                    total_failed += 1
                    print(f"           FAILED [{result['method']}]: {result['details']}")

                time.sleep(0.5)  # Rate limit between ICs

        # Display ungrouped legs
        if ungrouped:
            print(f"\n  Ungrouped legs ({len(ungrouped)}):")
            for pos in ungrouped:
                symbol = pos.get("symbol", "???")
                qty = float(pos.get("quantity", 0))
                side_label = "BUY_TO_CLOSE" if qty < 0 else "SELL_TO_CLOSE"
                print(f"    {symbol:30s}  qty={qty:>6.0f}  → {side_label}")

                if not args.execute:
                    print(f"      [DRY RUN] Would close individually @ market")
                    continue

                tag = f"CLOSE_ALL_{now.strftime('%Y%m%d_%H%M')}"
                result = close_single_leg(base_url, api_key, account_id, pos, tag)
                if result and result.get("order_id"):
                    total_closed += 1
                    print(f"      CLOSED: order_id={result['order_id']} [{result['status']}]")
                else:
                    total_failed += 1
                    print(f"      FAILED to close!")

                time.sleep(0.3)

    # Summary
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"  Iron Condors found:    {total_ics}")
    print(f"  Ungrouped legs found:  {total_ungrouped}")
    if args.execute:
        print(f"  Successfully closed:   {total_closed}")
        print(f"  Failed to close:       {total_failed}")
    else:
        print(f"  [DRY RUN] — no orders sent. Use --execute to close.")
    print(f"{'=' * 70}")

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
