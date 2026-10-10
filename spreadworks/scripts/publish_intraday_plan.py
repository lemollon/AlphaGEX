"""Atomically publish one morning plan and verify server-side parity."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("plan", type=Path, help="Path to the complete morning-plan JSON file")
    parser.add_argument("--base-url", required=True, help="SpreadWorks backend base URL")
    args = parser.parse_args()

    token = os.getenv("INTRADAY_WATCH_API_TOKEN", "").strip()
    if not token:
        print("INTRADAY_WATCH_API_TOKEN is not configured", file=sys.stderr)
        return 2
    try:
        payload = json.loads(args.plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Unable to read plan: {exc}", file=sys.stderr)
        return 2
    if "symbols" not in payload or "setups" not in payload or "trading_date" not in payload:
        print("Plan must contain trading_date, symbols, and setups", file=sys.stderr)
        return 2

    endpoint = args.base_url.rstrip("/") + "/api/spreadworks/intraday-watch/plan"
    headers = {"X-Intraday-Watch-Token": token}
    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        registered = response.json()
        digest = registered.get("plan_hash")
        parity = registered.get("parity") or {}
        counts_match = (
            registered.get("registered_symbol_count") == len(payload["symbols"])
            and registered.get("registered_setup_count") == len(payload["setups"])
        )
        if not parity.get("valid") or not counts_match or not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeError("server did not confirm exact plan parity and counts")
        verify = requests.get(
            endpoint, params={"trading_date": payload["trading_date"]}, timeout=30
        )
        verify.raise_for_status()
        stored = verify.json()
        if stored.get("plan_hash") != digest:
            raise RuntimeError("stored plan hash does not match registration response")
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        print(f"Plan publication failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Plan registered date={payload['trading_date']} "
        f"symbols={registered['registered_symbol_count']} "
        f"setups={registered['registered_setup_count']} hash={digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
