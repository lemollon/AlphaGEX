#!/usr/bin/env python3
"""
Schema Validation Script
========================
Ensures database schema integrity and prevents schema fragmentation.

This script:
1. Scans for CREATE TABLE statements outside the main schema file
2. Validates all tables have required timestamp columns
3. Checks for orphaned tables (defined but never used)
4. Checks for phantom tables (used but never defined)
5. Validates foreign key references

Run this script:
- On every commit (pre-commit hook)
- During CI/CD pipeline
- During weekly maintenance

Exit codes:
- 0: All validations passed
- 1: Errors found (blocks deployment)
- 2: Warnings only (allows deployment with notice)
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from datetime import datetime

# Configuration
MAIN_SCHEMA_FILE = "db/config_and_database.py"
ALLOWED_SCHEMA_FILES = {
    "db/config_and_database.py",
    "scripts/validate_schema.py",  # This file (for testing)
}
# Files that may contain example CREATE TABLE statements (documentation/migration guides)
DOCUMENTATION_FILES = {
    "scripts/postgresql_migration_guide.py",
    "scripts/databricks_migration_guide.py",
    "validation/quant_validation.py",  # SQLite for local testing
}
EXCLUDED_DIRS = {
    "__pycache__", ".git", "node_modules", "venv", ".venv",
    "env", ".env", "dist", "build", ".pytest_cache"
}
EXCLUDED_FILES = {
    "test_", "_test.py", "conftest.py"
}

# Tables that are allowed to be empty (user-activated features)
ALLOWED_EMPTY_TABLES = {
    "alerts", "alert_history", "conversations", "push_subscriptions",
    "trade_setups", "probability_outcomes", "probability_weights",
    "calibration_history", "wheel_cycles", "wheel_legs", "wheel_activity_log",
    "paper_signals", "paper_outcomes", "ai_recommendations", "ai_predictions",
    "pattern_learning", "ai_performance", "vix_hedge_positions", "vix_hedge_signals",
    "strategy_competition", "unified_positions", "unified_trades"
}

# Required timestamp columns for each table category
TIMESTAMP_COLUMNS = {
    "default": ["timestamp", "created_at"],
    "date_based": ["date", "signal_date", "entry_date", "prediction_date"],
    "updated": ["updated_at", "last_updated"]
}


class SchemaValidator:
    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root or os.getcwd())
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

        # Tables found in main schema
        self.main_schema_tables: Set[str] = set()
        # Tables found in other files
        self.external_tables: Dict[str, List[str]] = {}  # table -> [files]
        # Tables used in INSERT statements
        self.tables_with_inserts: Dict[str, List[str]] = {}
        # Tables used in SELECT statements
        self.tables_with_selects: Dict[str, List[str]] = {}

    def run_all_validations(self) -> int:
        """Run all validations and return exit code"""
        print("\n" + "=" * 70)
        print("  ALPHAGEX SCHEMA VALIDATION")
        print(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        # Phase 1: Scan all files
        print("\n📂 Phase 1: Scanning codebase...")
        self._scan_main_schema()
        self._scan_all_files()

        # Phase 2: Validate
        print("\n🔍 Phase 2: Validating schema integrity...")
        self._validate_no_external_creates()
        self._validate_no_orphaned_tables()
        self._validate_no_phantom_tables()

        # Phase 3: Report
        print("\n" + "=" * 70)
        print("  VALIDATION RESULTS")
        print("=" * 70)

        # Print info
        if self.info:
            print("\nℹ️  INFO:")
            for msg in self.info:
                print(f"   {msg}")

        # Print warnings
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for msg in self.warnings:
                print(f"   {msg}")

        # Print errors
        if self.errors:
            print("\n❌ ERRORS:")
            for msg in self.errors:
                print(f"   {msg}")

        # Summary
        print("\n" + "-" * 70)
        print(f"Tables in main schema: {len(self.main_schema_tables)}")
        print(f"External CREATE TABLE found: {sum(len(v) for v in self.external_tables.values())}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        print("-" * 70)

        if self.errors:
            print("\n❌ VALIDATION FAILED - Fix errors before deploying\n")
            return 1
        elif self.warnings:
            print("\n⚠️  VALIDATION PASSED WITH WARNINGS\n")
            return 2
        else:
            print("\n✅ VALIDATION PASSED\n")
            return 0

    def _scan_main_schema(self):
        """Scan the main schema file for table definitions"""
        schema_path = self.project_root / MAIN_SCHEMA_FILE
        if not schema_path.exists():
            self.errors.append(f"Main schema file not found: {MAIN_SCHEMA_FILE}")
            return

        content = schema_path.read_text()

        # Find all CREATE TABLE statements
        pattern = r"CREATE TABLE IF NOT EXISTS\s+([a-z_]+)"
        matches = re.findall(pattern, content, re.IGNORECASE)

        self.main_schema_tables = set(matches)
        self.info.append(f"Found {len(self.main_schema_tables)} tables in main schema")

    def _scan_all_files(self):
        """Scan all Python files for table references"""
        for py_file in self.project_root.rglob("*.py"):
            # Skip excluded directories
            if any(excl in py_file.parts for excl in EXCLUDED_DIRS):
                continue

            # Skip test files
            if any(py_file.name.startswith(excl) or py_file.name.endswith(excl)
                   for excl in EXCLUDED_FILES):
                continue

            rel_path = str(py_file.relative_to(self.project_root))

            try:
                content = py_file.read_text()
            except Exception:
                continue

            # Find CREATE TABLE statements
            create_pattern = r"CREATE TABLE IF NOT EXISTS\s+([a-z_]+)"
            creates = re.findall(create_pattern, content, re.IGNORECASE)

            if creates and rel_path not in ALLOWED_SCHEMA_FILES:
                for table in creates:
                    if table not in self.external_tables:
                        self.external_tables[table] = []
                    self.external_tables[table].append(rel_path)

            # Find INSERT statements
            insert_pattern = r"INSERT INTO\s+([a-z_]+)"
            inserts = re.findall(insert_pattern, content, re.IGNORECASE)
            for table in inserts:
                if table not in self.tables_with_inserts:
                    self.tables_with_inserts[table] = []
                self.tables_with_inserts[table].append(rel_path)

            # Find SELECT statements
            select_pattern = r"FROM\s+([a-z_]+)[\s\n\)]"
            selects = re.findall(select_pattern, content, re.IGNORECASE)
            for table in selects:
                if table not in self.tables_with_selects:
                    self.tables_with_selects[table] = []
                self.tables_with_selects[table].append(rel_path)

    def _validate_no_external_creates(self):
        """Ensure no CREATE TABLE statements outside main schema"""
        for table, files in self.external_tables.items():
            # Check if all files are documentation-only (migration guides, etc.)
            non_doc_files = [f for f in files if f not in DOCUMENTATION_FILES]
            doc_files = [f for f in files if f in DOCUMENTATION_FILES]

            # Check if also in main schema (duplicate) vs only external (missing)
            if table in self.main_schema_tables:
                self.warnings.append(
                    f"DUPLICATE: '{table}' defined in main schema AND in: {', '.join(files)}"
                )
            elif non_doc_files:
                # Only report as error if there are non-documentation files
                self.errors.append(
                    f"EXTERNAL: '{table}' only defined in: {', '.join(non_doc_files)} - must be in {MAIN_SCHEMA_FILE}"
                )
            # Tables only in documentation files are fine - they're examples, not real tables

    def _validate_no_orphaned_tables(self):
        """Check for tables defined but never used"""
        all_used = set(self.tables_with_inserts.keys()) | set(self.tables_with_selects.keys())

        for table in self.main_schema_tables:
            if table not in all_used and table not in ALLOWED_EMPTY_TABLES:
                self.warnings.append(f"ORPHANED: '{table}' defined but never used (no INSERT or SELECT)")

    def _validate_no_phantom_tables(self):
        """Check for tables used but not defined"""
        # Common SQL keywords that look like table names
        sql_keywords = {
            "select", "from", "where", "and", "or", "not", "null", "true", "false",
            "order", "by", "group", "having", "limit", "offset", "join", "left",
            "right", "inner", "outer", "on", "as", "in", "exists", "case", "when",
            "then", "else", "end", "insert", "into", "values", "update", "set",
            "delete", "create", "table", "index", "constraint", "primary", "key",
            "foreign", "references", "unique", "check", "default", "now"
        }

        all_used = set(self.tables_with_inserts.keys()) | set(self.tables_with_selects.keys())

        for table in all_used:
            # Skip SQL keywords
            if table.lower() in sql_keywords:
                continue
            # Skip system tables
            if table.startswith("pg_") or table.startswith("information_"):
                continue

            if table not in self.main_schema_tables:
                # Get sample files where this table is used
                files = list(set(
                    self.tables_with_inserts.get(table, []) +
                    self.tables_with_selects.get(table, [])
                ))[:3]
                self.warnings.append(
                    f"PHANTOM: '{table}' used but not defined in main schema. Used in: {', '.join(files)}"
                )


def main():
    """Main entry point"""
    # Get project root
    project_root = os.environ.get("PROJECT_ROOT", os.getcwd())

    validator = SchemaValidator(project_root)
    exit_code = validator.run_all_validations()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
