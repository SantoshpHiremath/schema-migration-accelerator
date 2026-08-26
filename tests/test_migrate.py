"""
tests/test_migrate.py
------------------------

Tests the migration pipeline against the real sample legacy database
(via legacy_schema.create_and_seed_legacy_db), covering dry-run vs.
real-run behavior, per-record error isolation, and customer
deduplication.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.legacy_schema import create_and_seed_legacy_db
from src.target_schema import create_target_db
from src.migrate import run_migration


@pytest.fixture
def legacy_db(tmp_path):
    return create_and_seed_legacy_db(tmp_path / "legacy.db")


@pytest.fixture
def target_db_path(tmp_path):
    path = tmp_path / "target.db"
    create_target_db(path)
    return path


class TestDryRun:
    def test_dry_run_reports_expected_totals_without_writing(self, legacy_db, target_db_path):
        report = run_migration(legacy_db, target_db_path, dry_run=True)

        assert report.dry_run is True
        assert report.total_legacy_records == 10
        # Record 5 (empty premium) and record 10 (corrupt premium) should fail.
        assert report.failed_count == 2
        assert report.migrated_policy_count == 8

        # Target DB must be completely untouched by a dry run.
        conn = sqlite3.connect(target_db_path)
        count = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
        conn.close()
        assert count == 0

    def test_dry_run_reports_correct_error_reasons(self, legacy_db, target_db_path):
        report = run_migration(legacy_db, target_db_path, dry_run=True)
        failed_ids = {e.legacy_record_id: e.reason for e in report.errors}

        assert 5 in failed_ids
        assert "premium_amount" in failed_ids[5]
        assert 10 in failed_ids
        assert "not_a_number" in failed_ids[10]

    def test_dry_run_counts_deduplicated_customers(self, legacy_db, target_db_path):
        """Records 1 and 9 are the same customer (Anna Mueller) with two
        different policies -- the dry-run's unique-customer count must
        reflect deduplication, not just count successfully-transformed
        rows 1:1."""
        report = run_migration(legacy_db, target_db_path, dry_run=True)
        # 8 successful records, but records 1 and 9 collapse to 1 customer
        # -> 7 unique customers.
        assert report.unique_customers_created == 7


class TestRealRun:
    def test_real_run_writes_expected_row_counts(self, legacy_db, target_db_path):
        report = run_migration(legacy_db, target_db_path, dry_run=False)

        conn = sqlite3.connect(target_db_path)
        policy_count = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
        customer_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        address_count = conn.execute("SELECT COUNT(*) FROM addresses").fetchone()[0]
        conn.close()

        assert report.dry_run is False
        assert policy_count == 8
        assert customer_count == 7
        assert address_count == 7  # one address per unique customer

    def test_failed_records_do_not_appear_in_target(self, legacy_db, target_db_path):
        run_migration(legacy_db, target_db_path, dry_run=False)

        conn = sqlite3.connect(target_db_path)
        source_ids = {row[0] for row in conn.execute("SELECT source_legacy_record_id FROM policies")}
        conn.close()

        assert 5 not in source_ids   # empty premium
        assert 10 not in source_ids  # corrupt premium

    def test_duplicate_customer_shares_single_customer_row(self, legacy_db, target_db_path):
        """Anna Mueller (records 1 and 9) must end up with exactly one
        customers row and two policies rows pointing at it -- proving
        the dedup key actually merges rather than just counting right
        by coincidence."""
        run_migration(legacy_db, target_db_path, dry_run=False)

        conn = sqlite3.connect(target_db_path)
        conn.row_factory = sqlite3.Row
        anna = conn.execute("SELECT * FROM customers WHERE full_name = 'Anna Mueller'").fetchall()
        assert len(anna) == 1

        policies = conn.execute(
            "SELECT * FROM policies WHERE customer_id = ?", (anna[0]["customer_id"],)
        ).fetchall()
        conn.close()
        assert len(policies) == 2
        assert {p["source_legacy_record_id"] for p in policies} == {1, 9}

    def test_date_and_premium_fields_normalized_correctly_end_to_end(self, legacy_db, target_db_path):
        """Spot-checks one specific migrated record by hand rather than
        only trusting aggregate counts -- record 2 (schmidt thomas, date
        '14.06.2020', premium '1290.00')."""
        run_migration(legacy_db, target_db_path, dry_run=False)

        conn = sqlite3.connect(target_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM policies WHERE source_legacy_record_id = 2"
        ).fetchone()
        conn.close()

        assert row["signup_date"] == "2020-06-14"
        assert row["premium_amount_cents"] == 129000

    def test_dry_run_and_real_run_agree_on_totals(self, legacy_db, target_db_path):
        """The dry-run report is a promise about what a real run will
        do -- this test holds that promise to account by running both
        against fresh copies and comparing."""
        dry_report = run_migration(legacy_db, target_db_path, dry_run=True)
        real_report = run_migration(legacy_db, target_db_path, dry_run=False)

        assert dry_report.migrated_policy_count == real_report.migrated_policy_count
        assert dry_report.unique_customers_created == real_report.unique_customers_created
        assert dry_report.failed_count == real_report.failed_count
