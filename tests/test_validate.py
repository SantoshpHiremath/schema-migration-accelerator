"""
tests/test_validate.py
-------------------------

Tests the independent post-migration validator, including a
deliberately corrupted target database to confirm validate_migration
actually catches a real discrepancy rather than always reporting
success. This mirrors the project portfolio's standard regression-test
discipline: prove the check can fail before trusting that it passing
means something.
"""

from __future__ import annotations

import sqlite3

import pytest

from src.legacy_schema import create_and_seed_legacy_db
from src.target_schema import create_target_db
from src.migrate import run_migration
from src.validate import validate_migration


@pytest.fixture
def legacy_db(tmp_path):
    return create_and_seed_legacy_db(tmp_path / "legacy.db")


@pytest.fixture
def target_db_path(tmp_path):
    path = tmp_path / "target.db"
    create_target_db(path)
    return path


def test_validate_raises_on_dry_run_report(legacy_db, target_db_path):
    report = run_migration(legacy_db, target_db_path, dry_run=True)
    with pytest.raises(ValueError):
        validate_migration(legacy_db, target_db_path, report)


def test_validate_passes_on_a_correct_real_migration(legacy_db, target_db_path):
    report = run_migration(legacy_db, target_db_path, dry_run=False)
    result = validate_migration(legacy_db, target_db_path, report)

    assert result.ok is True
    assert result.row_count_ok is True
    assert result.checksum_ok is True
    assert result.expected_policy_count == result.actual_policy_count == 8
    assert result.orphaned_source_ids == []
    assert result.leaked_failed_ids == []


def test_validate_checksum_matches_hand_computed_sum(legacy_db, target_db_path):
    """Independently confirms the checksum against a hand-summed value
    from the known sample data, not just against the migration's own
    internal accounting."""
    report = run_migration(legacy_db, target_db_path, dry_run=False)
    result = validate_migration(legacy_db, target_db_path, report)

    # Sum of the 8 successfully-migrated premiums from SAMPLE_RECORDS,
    # in cents: 482.50 + 1290.00 + 615.75 + 2200.00 + 530.00 + 980.20 +
    # 1750.00 + 3100.00 = 10948.45
    assert result.expected_premium_cents_sum == 1094845
    assert result.actual_premium_cents_sum == 1094845


def test_validate_catches_a_deliberately_corrupted_target_row_count(legacy_db, target_db_path):
    """Deliberately breaks the migrated data (deletes a policy row
    behind the validator's back, simulating a partial-write bug) and
    confirms validate_migration actually reports failure -- proving
    the check has teeth rather than trivially passing no matter what."""
    report = run_migration(legacy_db, target_db_path, dry_run=False)

    conn = sqlite3.connect(target_db_path)
    conn.execute("DELETE FROM policies WHERE source_legacy_record_id = 2")
    conn.commit()
    conn.close()

    result = validate_migration(legacy_db, target_db_path, report)

    assert result.ok is False
    assert result.row_count_ok is False
    assert result.actual_policy_count == 7
    assert result.expected_policy_count == 8


def test_validate_catches_a_deliberately_corrupted_premium_checksum(legacy_db, target_db_path):
    """Same idea, but corrupts a premium value instead of deleting a
    row -- proving the checksum check is independently meaningful and
    not just a restatement of the row-count check."""
    report = run_migration(legacy_db, target_db_path, dry_run=False)

    conn = sqlite3.connect(target_db_path)
    conn.execute(
        "UPDATE policies SET premium_amount_cents = premium_amount_cents + 100000 WHERE source_legacy_record_id = 2"
    )
    conn.commit()
    conn.close()

    result = validate_migration(legacy_db, target_db_path, report)

    assert result.ok is False
    assert result.checksum_ok is True or result.checksum_ok is False  # sanity: attribute exists
    assert result.checksum_ok is False
    assert result.row_count_ok is True  # row count is unaffected by this corruption


def test_validate_catches_a_failed_record_that_leaked_into_target(legacy_db, target_db_path):
    """Simulates the worst-case migration bug: a record that should
    have been rejected (record 10, corrupt premium) somehow gets
    written to target anyway. Confirms the validator's leaked-ids check
    actually fires."""
    report = run_migration(legacy_db, target_db_path, dry_run=False)

    conn = sqlite3.connect(target_db_path)
    cur = conn.execute(
        "INSERT INTO customers (full_name, email, phone) VALUES ('Nora Klein', 'nora.klein@example.com', NULL)"
    )
    customer_id = cur.lastrowid
    conn.execute(
        """INSERT INTO policies
           (customer_id, policy_number, policy_type, premium_amount_cents, signup_date, source_legacy_record_id)
           VALUES (?, 'POL-1010', 'auto', 0, '2022-01-15', 10)""",
        (customer_id,),
    )
    conn.commit()
    conn.close()

    result = validate_migration(legacy_db, target_db_path, report)

    assert result.ok is False
    assert 10 in result.leaked_failed_ids
