
# Reset sandbox cache so new keys/account IDs are picked up
_sandbox_accounts = None
_account_id_cache.clear()


# ---------------------------------------------------------------------------
#  Sandbox Orphan Cleanup
# ---------------------------------------------------------------------------


def _run_sandbox_orphan_cleanup() -> None:
    """Close stranded sandbox positions that weren't closed with the paper position.

    Run via: SCANNER_MODE=cleanup python ironforge_scanner.py
    Or call directly from a Databricks notebook cell.

    Queries each sandbox account for open option positions, then closes them
    with market orders.
    """
    print("=" * 60)
    print("  SANDBOX ORPHAN CLEANUP")
    print("=" * 60)

    accounts = _get_sandbox_accounts()
    if not accounts:
        print("  No sandbox accounts configured")
        return

    for acct in accounts:
        acct_id = _get_account_id_for_key(acct["api_key"])
        if not acct_id:
            print(f"  [{acct['name']}] SKIP — no account_id resolved")
            continue

        print(f"\n  [{acct['name']}] Account: {acct_id}")

        # Query open positions from Tradier sandbox
        data = _sandbox_get(f"/accounts/{acct_id}/positions", None, acct["api_key"])
        if not data:
            print(f"  [{acct['name']}] No position data returned")
            continue

        positions = data.get("positions", {})
        if positions == "null" or not positions:
            print(f"  [{acct['name']}] No open positions — clean")
            continue

        pos_list = positions.get("position", [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]

        if not pos_list:
            print(f"  [{acct['name']}] No open positions — clean")
            continue

        print(f"  [{acct['name']}] Found {len(pos_list)} open position(s):")
        for p in pos_list:
            symbol = p.get("symbol", "?")
            qty = p.get("quantity", 0)
            cost_basis = p.get("cost_basis", 0)
            print(f"    {symbol} qty={qty} cost_basis={cost_basis}")

        # Close each position with a market order
        for p in pos_list:
            symbol = p.get("symbol", "")
            qty = p.get("quantity", 0)
            if not symbol or qty == 0:
                continue

            # Determine close side: positive qty = long (sell_to_close),
            # negative qty = short (buy_to_close)
            if qty > 0:
                side = "sell_to_close"
                close_qty = qty
            else:
                side = "buy_to_close"
                close_qty = abs(qty)

            close_body = {
                "class": "option",
                "symbol": symbol.split(" ")[0] if " " in symbol else "SPY",
                "option_symbol": symbol,
                "side": side,
                "quantity": str(close_qty),
                "type": "market",
                "duration": "day",
            }

            result = _sandbox_post(
                f"/accounts/{acct_id}/orders", close_body, acct["api_key"],
            )
            order_id = result.get("order", {}).get("id") if result else None
            if order_id:
                print(f"    CLOSED: {symbol} {side} x{close_qty} → order_id={order_id}")
            else:
                print(f"    FAILED: {symbol} {side} x{close_qty} — check logs for HTTP error")

    print(f"\n{'=' * 60}")
    print("  Cleanup complete")
    print("=" * 60)


def main() -> None:
    """Single scan — called by Databricks Job every 5 minutes.

    In Job context (SCANNER_MODE=single), runs one scan cycle and exits.
    The Databricks Job scheduler handles the 5-minute repeat.

    In notebook context (SCANNER_MODE=loop), runs in an infinite loop
    with a 5-minute sleep between cycles.
    """
    try:
        ct = get_central_time()
        print(f"IronForge scan starting at {ct.strftime('%Y-%m-%d %H:%M:%S')} CT")
        print(f"  Catalog: {CATALOG} | Schema: {SCHEMA} | Tradier: {'OK' if is_tradier_configured() else 'MISSING'}")
        accounts = _get_sandbox_accounts_lazy()
        print(f"  Sandbox accounts: {len(accounts)}")
        for acct in accounts:
            acct_id = acct.get("account_id") or "auto-discover"
            print(f"    {acct['name']}: key={acct['api_key'][:6]}... account={acct_id}")
        log.info(
            f"IronForge scan starting at {ct.strftime('%Y-%m-%d %H:%M:%S')} CT "
            f"| Catalog: {CATALOG} | Schema: {SCHEMA} "
            f"| Tradier: {'OK' if is_tradier_configured() else 'MISSING'}"
        )

        if not is_market_open(ct):
            if is_in_warmup_window(ct):
                # Pre-market warm-up: wait for 8:30 so the cluster stays alive
                from zoneinfo import ZoneInfo
                market_open = ct.replace(hour=8, minute=30, second=0, microsecond=0)
                wait_secs = max(0, (market_open - ct).total_seconds())
                print(f"  Pre-market warm-up — waiting {int(wait_secs)}s for market open")
                log.info(
                    f"Pre-market warm-up window ({ct.strftime('%H:%M')} CT) — "
                    f"cluster warm, waiting {int(wait_secs)}s for market open"
                )
                if wait_secs > 0:
                    time.sleep(wait_secs)
                # Re-check time after sleeping (should now be ~8:30)
                ct = get_central_time()
                print(f"  Warm-up complete — now {ct.strftime('%H:%M:%S')} CT")
                log.info(f"Warm-up complete — now {ct.strftime('%H:%M:%S')} CT, proceeding to scan")
            else:
                print(f"  Market closed ({ct.strftime('%H:%M')} CT) — exiting")
                log.info(
                    f"Market closed ({ct.strftime('%H:%M')} CT, "
                    f"{'weekend' if ct.weekday() >= 5 else 'outside 8:30-15:00'}) — exiting"
                )
                return

        print("  Running scan cycle...")
        run_scan_cycle()
        print("  Scan complete — exiting")
        log.info("Scan complete — exiting")

    except Exception as e:
        print(f"  MAIN ERROR: {e}")
        import traceback as tb
        tb.print_exc()


# Entry point: single-scan (Job) vs loop (notebook testing)
_scanner_mode = os.environ.get("SCANNER_MODE", "single")

if _scanner_mode == "loop":
    # Notebook testing mode — infinite loop with 5-min sleep
    print("Starting in LOOP mode (notebook testing)")
    while True:
        main()
        time.sleep(SCAN_INTERVAL)
elif _scanner_mode == "cleanup":
    # Orphan cleanup mode — close stranded sandbox positions
    _run_sandbox_orphan_cleanup()
else:
    # Job mode — single scan and exit
    main()
