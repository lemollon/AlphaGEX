"""
Tastytrade API Routes
Connection testing and future HERACLES bot integration
"""

import os
import requests
from datetime import datetime
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Tastytrade"])

# Tastytrade API endpoints
TASTYTRADE_BASE_URL = "https://api.tastytrade.com"
TASTYTRADE_SANDBOX_URL = "https://api.cert.tastytrade.com"


def get_tastytrade_session():
    """Authenticate with Tastytrade and return session token"""
    username = os.environ.get("TASTYTRADE_USERNAME")
    password = os.environ.get("TASTYTRADE_PASSWORD")

    if not username or not password:
        raise HTTPException(
            status_code=500,
            detail="TASTYTRADE_USERNAME and TASTYTRADE_PASSWORD not configured"
        )

    response = requests.post(
        f"{TASTYTRADE_BASE_URL}/sessions",
        json={
            "login": username,
            "password": password,
            "remember-me": True
        },
        headers={"Content-Type": "application/json"},
        timeout=30
    )

    if response.status_code == 201:
        data = response.json()
        return data.get("data", {}).get("session-token")
    else:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Tastytrade authentication failed: {response.text[:500]}"
        )


@router.get("/api/tastytrade/test-connection")
async def test_tastytrade_connection():
    """
    Test Tastytrade API connection
    Verifies credentials, account access, and futures capability
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "status": "testing",
        "checks": {}
    }

    # Check 1: Environment variables
    username = os.environ.get("TASTYTRADE_USERNAME")
    password = os.environ.get("TASTYTRADE_PASSWORD")
    account_id = os.environ.get("TASTYTRADE_ACCOUNT_ID")
    client_id = os.environ.get("TASTYTRADE_CLIENT_ID")

    results["checks"]["environment"] = {
        "username": bool(username),
        "password": bool(password),
        "account_id": account_id or "NOT SET",
        "client_id": bool(client_id)
    }

    if not username or not password:
        results["status"] = "failed"
        results["error"] = "Missing TASTYTRADE_USERNAME or TASTYTRADE_PASSWORD"
        return results

    # Check 2: Authentication
    try:
        session_token = get_tastytrade_session()
        results["checks"]["authentication"] = {
            "success": True,
            "token_preview": session_token[:20] + "..." if session_token else None
        }
    except HTTPException as e:
        results["status"] = "failed"
        results["checks"]["authentication"] = {
            "success": False,
            "error": str(e.detail)
        }
        return results

    headers = {
        "Authorization": session_token,
        "Content-Type": "application/json"
    }

    # Check 3: Account access
    try:
        account_response = requests.get(
            f"{TASTYTRADE_BASE_URL}/customers/me/accounts",
            headers=headers,
            timeout=30
        )

        if account_response.status_code == 200:
            accounts = account_response.json().get("data", {}).get("items", [])
            account_list = []
            target_found = False
            futures_enabled = False

            for acc in accounts:
                acc_info = acc.get("account", {})
                acc_num = acc_info.get("account-number")
                is_futures = acc_info.get("is-futures-enabled", False)

                account_list.append({
                    "account_number": acc_num,
                    "type": acc_info.get("account-type-name"),
                    "margin_or_cash": acc_info.get("margin-or-cash"),
                    "futures_enabled": is_futures
                })

                if acc_num == account_id:
                    target_found = True
                    futures_enabled = is_futures

            results["checks"]["accounts"] = {
                "success": True,
                "count": len(accounts),
                "accounts": account_list,
                "target_account_found": target_found,
                "target_futures_enabled": futures_enabled
            }
        else:
            results["checks"]["accounts"] = {
                "success": False,
                "error": f"Status {account_response.status_code}"
            }
    except Exception as e:
        results["checks"]["accounts"] = {
            "success": False,
            "error": str(e)
        }

    # Check 4: Account balances
    if account_id:
        try:
            balance_response = requests.get(
                f"{TASTYTRADE_BASE_URL}/accounts/{account_id}/balances",
                headers=headers,
                timeout=30
            )

            if balance_response.status_code == 200:
                balances = balance_response.json().get("data", {})
                results["checks"]["balances"] = {
                    "success": True,
                    "net_liquidating_value": balances.get("net-liquidating-value"),
                    "cash_balance": balances.get("cash-balance"),
                    "derivative_buying_power": balances.get("derivative-buying-power"),
                    "futures_buying_power": balances.get("futures-overnight-margin-requirement")
                }
            else:
                results["checks"]["balances"] = {
                    "success": False,
                    "error": f"Status {balance_response.status_code}"
                }
        except Exception as e:
            results["checks"]["balances"] = {
                "success": False,
                "error": str(e)
            }

    # Check 5: MES futures lookup
    try:
        # Look up MES (Micro E-mini S&P 500) futures
        instrument_response = requests.get(
            f"{TASTYTRADE_BASE_URL}/instruments/futures",
            headers=headers,
            params={"symbol[]": "/MES"},
            timeout=30
        )

        if instrument_response.status_code == 200:
            instruments = instrument_response.json().get("data", {}).get("items", [])
            mes_contracts = []

            for inst in instruments[:5]:  # First 5 contracts
                mes_contracts.append({
                    "symbol": inst.get("symbol"),
                    "description": inst.get("description"),
                    "tick_size": inst.get("tick-size"),
                    "tick_value": inst.get("tick-value"),
                    "expiration": inst.get("expiration-date")
                })

            results["checks"]["mes_futures"] = {
                "success": True,
                "contracts_found": len(instruments),
                "contracts": mes_contracts
            }
        else:
            results["checks"]["mes_futures"] = {
                "success": False,
                "error": f"Status {instrument_response.status_code}"
            }
    except Exception as e:
        results["checks"]["mes_futures"] = {
            "success": False,
            "error": str(e)
        }

    # Overall status
    all_checks_passed = all(
        check.get("success", False)
        for check in results["checks"].values()
        if isinstance(check, dict) and "success" in check
    )

    results["status"] = "success" if all_checks_passed else "partial"
    results["ready_for_heracles"] = (
        results["checks"].get("authentication", {}).get("success", False) and
        results["checks"].get("accounts", {}).get("target_futures_enabled", False) and
        results["checks"].get("mes_futures", {}).get("success", False)
    )

    return results


@router.get("/api/tastytrade/mes-quote")
async def get_mes_quote():
    """Get current MES futures quote"""
    try:
        session_token = get_tastytrade_session()
        headers = {
            "Authorization": session_token,
            "Content-Type": "application/json"
        }

        # Get front month MES contract
        # Try common symbols
        symbols_to_try = ["/MESH6", "/MESM6", "/MESU6", "/MESZ6", "/MESH5", "/MESM5"]

        for symbol in symbols_to_try:
            quote_response = requests.get(
                f"{TASTYTRADE_BASE_URL}/market-data/quotes/{symbol}",
                headers=headers,
                timeout=10
            )

            if quote_response.status_code == 200:
                quote_data = quote_response.json().get("data", {})
                return {
                    "symbol": symbol,
                    "bid": quote_data.get("bid-price"),
                    "ask": quote_data.get("ask-price"),
                    "last": quote_data.get("last-price"),
                    "volume": quote_data.get("volume"),
                    "timestamp": datetime.now().isoformat()
                }

        # If REST quotes don't work, return info about DXFeed
        return {
            "status": "streaming_required",
            "message": "Real-time futures quotes require DXFeed websocket streaming",
            "note": "REST API quotes may not be available for futures symbols"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/tastytrade/account-positions")
async def get_account_positions():
    """Get current positions in Tastytrade account"""
    account_id = os.environ.get("TASTYTRADE_ACCOUNT_ID")
    if not account_id:
        raise HTTPException(status_code=500, detail="TASTYTRADE_ACCOUNT_ID not configured")

    try:
        session_token = get_tastytrade_session()
        headers = {
            "Authorization": session_token,
            "Content-Type": "application/json"
        }

        positions_response = requests.get(
            f"{TASTYTRADE_BASE_URL}/accounts/{account_id}/positions",
            headers=headers,
            timeout=30
        )

        if positions_response.status_code == 200:
            positions = positions_response.json().get("data", {}).get("items", [])
            return {
                "account_id": account_id,
                "position_count": len(positions),
                "positions": positions,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(
                status_code=positions_response.status_code,
                detail=f"Failed to fetch positions: {positions_response.text[:500]}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
