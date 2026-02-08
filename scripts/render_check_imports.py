#!/usr/bin/env python3
"""
Render Shell Script: Check All Python Imports

Run in Render shell:
    python scripts/render_check_imports.py
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}")
def warn(msg): print(f"[WARN] {msg}")

print("=" * 60)
print("CHECKING ALL PYTHON IMPORTS")
print("=" * 60)

errors = []

# Core dependencies
print("\n-- Core Dependencies --")
for mod in ["fastapi", "uvicorn", "psycopg2", "pydantic"]:
    try:
        __import__(mod)
        ok(mod)
    except ImportError as e:
        fail(f"{mod}: {e}")
        errors.append(mod)

# AI modules
print("\n-- AI Modules --")
ai_modules = [
    "ai.counselor_personality",
    "ai.counselor_tools",
    "ai.counselor_extended_thinking",
    "ai.counselor_learning_memory",
    "ai.counselor_knowledge",
]
for mod in ai_modules:
    try:
        __import__(mod)
        ok(mod)
    except ImportError as e:
        fail(f"{mod}: {e}")
        errors.append(mod)

# Backend routes
print("\n-- Backend Routes --")
routes = [
    "backend.api.routes.ai_routes",
    "backend.api.routes.fortress_routes",
    "backend.api.routes.solomon_routes",
    "backend.api.routes.gex_routes",
    "backend.api.routes.trader_routes",
]
for mod in routes:
    try:
        __import__(mod)
        ok(mod)
    except ImportError as e:
        fail(f"{mod}: {e}")
        errors.append(mod)

# Trading bots
print("\n-- Trading Bots --")
bots = [
    "trading.fortress_v2.trader",
    "trading.solomon_v2.trader",
]
for mod in bots:
    try:
        __import__(mod)
        ok(mod)
    except ImportError as e:
        warn(f"{mod}: {e}")  # Warning only - pandas may be missing

# Quant modules
print("\n-- Quant Modules --")
quant = [
    "quant.prophet_advisor",
]
for mod in quant:
    try:
        __import__(mod)
        ok(mod)
    except ImportError as e:
        warn(f"{mod}: {e}")

# Summary
print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} critical imports failed")
    print(f"  {', '.join(errors)}")
    sys.exit(1)
else:
    print("SUCCESS: All critical imports passed")
    sys.exit(0)
