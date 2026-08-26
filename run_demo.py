"""
run_demo.py
-------------

Entry point demonstrating the full accelerator end to end: seed a
legacy database, run a dry-run migration and print the report, then
run the real migration, validate it independently, and print the
validation result.

Usage:
    python run_demo.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from src.legacy_schema import create_and_seed_legacy_db
from src.target_schema import create_target_db
from src.migrate import run_migration
from src.validate import validate_migration


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        legacy_db = create_and_seed_legacy_db(tmpdir / "legacy.db")
        target_db = tmpdir / "target.db"
        create_target_db(target_db)

        print("=== DRY RUN ===")
        dry_report = run_migration(legacy_db, target_db, dry_run=True)
        print(f"Total legacy records:      {dry_report.total_legacy_records}")
        print(f"Would migrate:             {dry_report.migrated_policy_count}")
        print(f"Unique customers created:  {dry_report.unique_customers_created}")
        print(f"Would fail:                {dry_report.failed_count}")
        for err in dry_report.errors:
            print(f"  - record {err.legacy_record_id}: {err.reason}")

        print("\n=== REAL MIGRATION ===")
        real_report = run_migration(legacy_db, target_db, dry_run=False)
        print(f"Migrated {real_report.migrated_policy_count} policies across "
              f"{real_report.unique_customers_created} unique customers; "
              f"{real_report.failed_count} records failed and were skipped.")

        print("\n=== INDEPENDENT VALIDATION ===")
        result = validate_migration(legacy_db, target_db, real_report)
        print(f"Row count check:  {'PASS' if result.row_count_ok else 'FAIL'} "
              f"(expected {result.expected_policy_count}, got {result.actual_policy_count})")
        print(f"Checksum check:   {'PASS' if result.checksum_ok else 'FAIL'} "
              f"(expected {result.expected_premium_cents_sum} cents, got {result.actual_premium_cents_sum} cents)")
        print(f"Orphaned rows:    {result.orphaned_source_ids or 'none'}")
        print(f"Leaked failures:  {result.leaked_failed_ids or 'none'}")
        print(f"\nOverall: {'MIGRATION VALID' if result.ok else 'MIGRATION INVALID'}")

        return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
