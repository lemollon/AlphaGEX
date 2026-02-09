#!/usr/bin/env python3
"""
GIDEON Analysis - Run All Scripts
=================================
Master script to run all GIDEON analysis scripts.

Run: python scripts/gideon_analysis/run_all.py
"""

import os
import sys
import subprocess
from datetime import datetime

# Get the directory of this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# List of analysis scripts in order
SCRIPTS = [
    "01_trade_breakdown.py",
    "02_oracle_analysis.py",
    "03_flip_and_walls.py",
    "04_before_vs_after.py",
    "05_vix_analysis.py",
    "06_trade_reasoning.py",
]

def main():
    print("\n" + "="*80)
    print(" GIDEON COMPLETE ANALYSIS SUITE")
    print(f" Started: {datetime.now()}")
    print("="*80)

    # Change to project root
    os.chdir(PROJECT_ROOT)

    for script in SCRIPTS:
        script_path = os.path.join(SCRIPT_DIR, script)
        if os.path.exists(script_path):
            print(f"\n{'#'*80}")
            print(f"# RUNNING: {script}")
            print(f"{'#'*80}\n")

            result = subprocess.run(
                [sys.executable, script_path],
                cwd=PROJECT_ROOT
            )

            if result.returncode != 0:
                print(f"⚠️ Script {script} exited with code {result.returncode}")
        else:
            print(f"⚠️ Script not found: {script_path}")

    print("\n" + "="*80)
    print(" ANALYSIS COMPLETE")
    print(f" Finished: {datetime.now()}")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
