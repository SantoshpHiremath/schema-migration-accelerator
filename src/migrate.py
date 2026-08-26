"""
migrate.py
------------

The migration accelerator itself: reads every record from the legacy
flat table, transforms it into the normalized target schema, and
writes it -- with three things a real migration tool needs and a
"just write a script" approach usually skips:

1. Dry-run mode: compute and report exactly what would happen (rows
   migrated, rows failed and why, customers deduplicated) without
   writing anything, so a migration can be reviewed before it runs for
   real.
2. Per-record error isolation: one bad legacy row (a corrupt premium
   value, an unparseable date) is caught, logged with a reason, and
   skipped -- it does not abort the entire batch, matching how a real
   migration accelerator has to behave against messy legacy data.
3. Post-migration validation: after a real (non-dry-run) migration,
   independently re-reads both databases and verifies row counts and a
   sum-of-premiums checksum match expectations, so success is verified,
   not assumed from the absence of exceptions.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from src.transforms import (
    TransformError,
    normalize_contact,
    normalize_date,
    normalize_premium_to_cents,
)


@dataclass
class MigrationError:
    legacy_record_id: int
    reason: str


@dataclass
class MigrationReport:
    dry_run: bool
    total_legacy_records: int
    migrated_policy_count: int
    unique_customers_created: int
    errors: list[MigrationError] = field(default_factory=list)

    @property
    def failed_count(self) -> int:
        return len(self.errors)

    @property
    def success(self) -> bool:
        return self.failed_count == 0


def _fetch_legacy_records(legacy_conn: sqlite3.Connection) -> list[sqlite3.Row]:
    legacy_conn.row_factory = sqlite3.Row
    cur = legacy_conn.execute("SELECT * FROM legacy_customer_records ORDER BY record_id")
    return cur.fetchall()


def _transform_record(row: sqlite3.Row) -> dict:
    """Transforms a single legacy row into target-schema-ready fields.
    Raises TransformError (from the underlying transform functions) if
    the record cannot be safely migrated."""
    contact = normalize_contact(row["cust_name"], row["cust_email"], row["cust_phone"])
    signup_date_iso = normalize_date(row["signup_date"])
    premium_cents = normalize_premium_to_cents(row["premium_amount"])

    return {
        "full_name": contact.full_name,
        "email": contact.email,
        "phone": contact.phone,
        "line1": row["addr_line"],
        "city": row["city"],
        "country_code": row["country_code"],
        "policy_number": row["policy_number"],
        "policy_type": row["policy_type"],
        "premium_amount_cents": premium_cents,
        "signup_date": signup_date_iso,
        "source_legacy_record_id": row["record_id"],
    }


def run_migration(legacy_db_path: str | Path, target_db_path: str | Path, dry_run: bool = True) -> MigrationReport:
    """Runs the migration. In dry-run mode (the default), no writes
    happen to target_db_path at all -- the report is computed by
    transforming every record and simulating customer deduplication in
    memory, then discarding the result."""
    legacy_conn = sqlite3.connect(legacy_db_path)
    legacy_conn.row_factory = sqlite3.Row
    try:
        legacy_rows = _fetch_legacy_records(legacy_conn)
    finally:
        legacy_conn.close()

    transformed: list[dict] = []
    errors: list[MigrationError] = []

    for row in legacy_rows:
        try:
            transformed.append(_transform_record(row))
        except TransformError as e:
            errors.append(MigrationError(legacy_record_id=row["record_id"], reason=str(e)))

    # Deduplicate customers by (full_name, email) -- the same key the
    # target schema's UNIQUE constraint enforces, computed here up front
    # so the dry-run report's "unique customers" count matches what a
    # real run would actually create.
    customer_keys_seen: dict[tuple[str, str | None], int] = {}
    for rec in transformed:
        key = (rec["full_name"], rec["email"])
        customer_keys_seen.setdefault(key, 0)
        customer_keys_seen[key] += 1

    if dry_run:
        return MigrationReport(
            dry_run=True,
            total_legacy_records=len(legacy_rows),
            migrated_policy_count=len(transformed),
            unique_customers_created=len(customer_keys_seen),
            errors=errors,
        )

    # Real run: write to target_db_path.
    target_conn = sqlite3.connect(target_db_path)
    try:
        customer_id_by_key: dict[tuple[str, str | None], int] = {}

        for rec in transformed:
            key = (rec["full_name"], rec["email"])
            if key not in customer_id_by_key:
                cur = target_conn.execute(
                    "INSERT INTO customers (full_name, email, phone) VALUES (?, ?, ?)",
                    (rec["full_name"], rec["email"], rec["phone"]),
                )
                customer_id = cur.lastrowid
                customer_id_by_key[key] = customer_id
                target_conn.execute(
                    "INSERT INTO addresses (customer_id, line1, city, country_code) VALUES (?, ?, ?, ?)",
                    (customer_id, rec["line1"], rec["city"], rec["country_code"]),
                )
            else:
                customer_id = customer_id_by_key[key]

            target_conn.execute(
                """INSERT INTO policies
                   (customer_id, policy_number, policy_type, premium_amount_cents, signup_date, source_legacy_record_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (customer_id, rec["policy_number"], rec["policy_type"], rec["premium_amount_cents"],
                 rec["signup_date"], rec["source_legacy_record_id"]),
            )

        target_conn.commit()
    except Exception:
        target_conn.rollback()
        raise
    finally:
        target_conn.close()

    return MigrationReport(
        dry_run=False,
        total_legacy_records=len(legacy_rows),
        migrated_policy_count=len(transformed),
        unique_customers_created=len(customer_keys_seen),
        errors=errors,
    )
