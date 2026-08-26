"""
validate.py
-------------

Independent post-migration validation. Deliberately re-reads both
databases from scratch and recomputes checks rather than trusting the
MigrationReport returned by run_migration() -- the same principle as
this whole application portfolio's re-run-and-recheck discipline,
applied here as actual verification code instead of a manual step.

Two checks:
1. Row-count reconciliation: every successfully-transformed legacy
   record must correspond to exactly one policy row in the target,
   and every failed record must NOT appear in the target at all.
2. Premium checksum: sum of premium_amount_cents in the target must
   equal the sum of successfully-parsed premiums from the legacy
   table, computed independently in Python (not trusting the
   migration's own accounting).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.migrate import MigrationReport
from src.transforms import TransformError, normalize_premium_to_cents


@dataclass
class ValidationResult:
    row_count_ok: bool
    checksum_ok: bool
    expected_policy_count: int
    actual_policy_count: int
    expected_premium_cents_sum: int
    actual_premium_cents_sum: int
    orphaned_source_ids: list[int]  # migrated policies with no failed/legacy match (should be empty)
    leaked_failed_ids: list[int]    # failed legacy records that ended up in target anyway (should be empty)

    @property
    def ok(self) -> bool:
        return self.row_count_ok and self.checksum_ok and not self.orphaned_source_ids and not self.leaked_failed_ids


def validate_migration(legacy_db_path: str | Path, target_db_path: str | Path, report: MigrationReport) -> ValidationResult:
    if report.dry_run:
        raise ValueError("validate_migration cannot validate a dry-run report -- nothing was written to check")

    failed_ids = {e.legacy_record_id for e in report.errors}

    legacy_conn = sqlite3.connect(legacy_db_path)
    legacy_conn.row_factory = sqlite3.Row
    try:
        legacy_rows = legacy_conn.execute("SELECT record_id, premium_amount FROM legacy_customer_records").fetchall()
    finally:
        legacy_conn.close()

    expected_premium_sum = 0
    for row in legacy_rows:
        if row["record_id"] in failed_ids:
            continue
        try:
            expected_premium_sum += normalize_premium_to_cents(row["premium_amount"])
        except TransformError:
            # A record not in report.errors should always parse; if this
            # branch is hit it means the report and this independent
            # recheck disagree -- treated as a hard validation failure
            # further down via the count/checksum mismatch, not silently
            # skipped here.
            continue

    target_conn = sqlite3.connect(target_db_path)
    target_conn.row_factory = sqlite3.Row
    try:
        target_rows = target_conn.execute(
            "SELECT source_legacy_record_id, premium_amount_cents FROM policies"
        ).fetchall()
    finally:
        target_conn.close()

    actual_policy_count = len(target_rows)
    actual_premium_sum = sum(r["premium_amount_cents"] for r in target_rows)
    migrated_source_ids = {r["source_legacy_record_id"] for r in target_rows}

    expected_policy_count = len(legacy_rows) - len(failed_ids)

    orphaned_source_ids = sorted(migrated_source_ids - {r["record_id"] for r in legacy_rows})
    leaked_failed_ids = sorted(migrated_source_ids & failed_ids)

    return ValidationResult(
        row_count_ok=(actual_policy_count == expected_policy_count),
        checksum_ok=(actual_premium_sum == expected_premium_sum),
        expected_policy_count=expected_policy_count,
        actual_policy_count=actual_policy_count,
        expected_premium_cents_sum=expected_premium_sum,
        actual_premium_cents_sum=actual_premium_sum,
        orphaned_source_ids=orphaned_source_ids,
        leaked_failed_ids=leaked_failed_ids,
    )
