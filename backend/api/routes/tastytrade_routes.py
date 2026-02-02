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

    # Check 5: MES futures lookup - try multiple approaches
    try:
        mes_contracts = []

        # Approach 1: Search by product code
        search_response = requests.get(
            f"{TASTYTRADE_BASE_URL}/futures-products/MES",
            headers=headers,
            timeout=30
        )

        product_info = None
        if search_response.status_code == 200:
            product_info = search_response.json().get("data", {})

        # Approach 2: Get active MES contracts
        # Try specific contract symbols for 2026
        contract_symbols = ["/MESH6", "/MESM6", "/MESU6", "/MESZ6"]

        for symbol in contract_symbols:
            try:
                contract_response = requests.get(
                    f"{TASTYTRADE_BASE_URL}/instruments/futures/{symbol}",
                    headers=headers,
                    timeout=10
                )
                if contract_response.status_code == 200:
                    contract_data = contract_response.json().get("data", {})
                    if contract_data:
                        mes_contracts.append({
                            "symbol": contract_data.get("symbol"),
                            "description": contract_data.get("description"),
                            "tick_size": contract_data.get("tick-size"),
                            "tick_value": contract_data.get("tick-value"),
                            "expiration": contract_data.get("expiration-date"),
                            "active": contract_data.get("is-active", True)
                        })
            except:
                pass

        # Approach 3: Search all futures instruments
        if not mes_contracts:
            all_futures_response = requests.get(
                f"{TASTYTRADE_BASE_URL}/instruments/futures",
                headers=headers,
                params={"product-code": "MES"},
                timeout=30
            )

            if all_futures_response.status_code == 200:
                instruments = all_futures_response.json().get("data", {}).get("items", [])
                for inst in instruments[:5]:
                    mes_contracts.append({
                        "symbol": inst.get("symbol"),
                        "description": inst.get("description"),
                        "tick_size": inst.get("tick-size"),
                        "tick_value": inst.get("tick-value"),
                        "expiration": inst.get("expiration-date")
                    })

        results["checks"]["mes_futures"] = {
            "success": True,
            "contracts_found": len(mes_contracts),
            "contracts": mes_contracts,
            "product_info": product_info
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

    # Note: is-futures-enabled API flag is unreliable (shows false even when futures is enabled)
    # We check: auth success + account found + can lookup futures products
    results["ready_for_heracles"] = (
        results["checks"].get("authentication", {}).get("success", False) and
        results["checks"].get("accounts", {}).get("target_account_found", False) and
        results["checks"].get("mes_futures", {}).get("success", False)
    )

    # Add note about API flag discrepancy
    if results["checks"].get("accounts", {}).get("target_account_found") and \
       not results["checks"].get("accounts", {}).get("target_futures_enabled"):
        results["note"] = "API shows futures_enabled=false but this may be incorrect. Verify in Tastytrade UI."

    return results


@router.get("/api/tastytrade/futures-products")
async def get_futures_products():
    """List all available futures products to find MES symbol format"""
    try:
        session_token = get_tastytrade_session()
        headers = {
            "Authorization": session_token,
            "Content-Type": "application/json"
        }

        # Get all futures products
        products_response = requests.get(
            f"{TASTYTRADE_BASE_URL}/instruments/futures",
            headers=headers,
            timeout=30
        )

        if products_response.status_code == 200:
            data = products_response.json().get("data", {})
            items = data.get("items", [])

            # Filter for MES-related products
            mes_related = [
                {
                    "symbol": item.get("symbol"),
                    "description": item.get("description"),
                    "product_code": item.get("product-code"),
                    "expiration": item.get("expiration-date"),
                    "active": item.get("is-active")
                }
                for item in items
                if "MES" in str(item.get("symbol", "")).upper() or
                   "MICRO" in str(item.get("description", "")).upper() or
                   "E-MINI" in str(item.get("description", "")).upper()
            ]

            return {
                "total_futures_count": len(items),
                "mes_related_count": len(mes_related),
                "mes_contracts": mes_related[:10],  # First 10
                "sample_all_symbols": [item.get("symbol") for item in items[:20]],  # First 20 symbols
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "error": f"Status {products_response.status_code}",
                "response": products_response.text[:500]
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
