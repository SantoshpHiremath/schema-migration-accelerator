# schema-migration-accelerator

A real, tested Python data-migration accelerator: moves records from a
messy, denormalized "legacy" schema into a clean, normalized "target"
schema, with dry-run planning, per-record error isolation, and
independent post-migration validation — built to close a specific gap
for Allianz Services' "Intern (m/f/d) - AI Software Engineering"
posting (Job ID 104555), whose core ask (software components for
migration accelerators, used to help teams move faster and more
reliably between systems, platforms, and data models) wasn't covered
by anything else in my project portfolio.

## Why this project exists

Every other project in this portfolio does something adjacent to
software engineering, DevOps, or AI — but none of them actually
*migrate* data or a schema from one shape to another, which is the
literal, specific thing "migration accelerator" tooling does. Rather
than lean only on adjacent CI/CD and AI-integration evidence, I built
a small, real migration tool end to end: a legacy source schema, a
normalized target schema, transform logic that handles the kind of
inconsistent real-world data legacy systems actually contain, and —
critically — independent validation that a migration run actually
did what it claimed.

## What it actually does

1. **`src/legacy_schema.py`** — a synthetic "legacy" SQLite database:
   one flat, denormalized table modeled on how an older
   policy-administration or customer system often looks in practice.
   Deliberately messy: inconsistent name casing and "Last, First" vs.
   "first last" formats, four different date formats, a missing
   premium value, a corrupt non-numeric premium value, and one
   customer who appears twice (two policies, same person). **All data
   is synthetic, generated here — not real Allianz or any company's
   data.**
2. **`src/target_schema.py`** — a normalized target schema
   (`customers` / `addresses` / `policies`), the shape a modern system
   typically wants instead of repeating a customer's contact details
   on every row.
3. **`src/transforms.py`** — pure, independently-tested transform
   functions: name normalization (handles both legacy name formats),
   date normalization (handles all four legacy date formats into ISO
   8601), and premium normalization (string → integer cents, avoiding
   float rounding issues, rejecting non-numeric or negative values
   rather than silently coercing them to 0).
4. **`src/migrate.py`** — the migration pipeline itself, with three
   things a real migration accelerator needs:
   - **Dry-run mode** — computes and reports exactly what a migration
     *would* do (records migrated, records failed and why, customers
     deduplicated) without writing anything, so a migration can be
     reviewed before it runs for real.
   - **Per-record error isolation** — one bad legacy row doesn't abort
     the whole batch; it's caught, logged with a specific reason, and
     skipped.
   - **Customer deduplication** — records that resolve to the same
     normalized (name, email) share a single target customer row
     instead of creating duplicates.
5. **`src/validate.py`** — independent post-migration validation that
   re-reads both databases from scratch (not trusting the migration's
   own internal accounting) and checks: row counts reconcile exactly,
   a premium checksum matches a value computed independently in
   Python, no failed record leaked into the target, and no orphaned
   row exists in the target with no legacy source.

## Verified output (real run, not illustrative)

```
$ python run_demo.py
=== DRY RUN ===
Total legacy records:      10
Would migrate:             8
Unique customers created:  7
Would fail:                2
  - record 5: premium_amount is missing or empty
  - record 10: premium_amount is not a valid decimal number: 'not_a_number'

=== REAL MIGRATION ===
Migrated 8 policies across 7 unique customers; 2 records failed and were skipped.

=== INDEPENDENT VALIDATION ===
Row count check:  PASS (expected 8, got 8)
Checksum check:   PASS (expected 1094845 cents, got 1094845 cents)
Orphaned rows:    none
Leaked failures:  none

Overall: MIGRATION VALID
```

Note the dry-run report and the real run agree exactly (8 migrated, 7
unique customers, 2 failures) — the dry run is a genuine prediction of
the real run's outcome, not a separate, disconnected code path; this
is directly tested in `test_dry_run_and_real_run_agree_on_totals`.

## Testing

41 tests, all passing, covering: every legacy name/date/premium format
variant and its error cases, dry-run vs. real-run behavior, per-record
error isolation, customer deduplication (including a hand-verified
spot-check that Anna Mueller's two policies correctly share one
customer row), and independent post-migration validation.

```
pip install -r requirements.txt
pytest -v
```

```
============================== 41 passed in <1s ===============================
```

### Regression-test discipline

During development, the date-normalization logic for the `DD.MM.YYYY`
format was deliberately broken (day and month swapped in the parsing
logic) to confirm `test_dot_format_dmy` actually catches a wrong
transform rather than trivially passing. It failed as expected
(`date has out-of-range month/day: '14.06.2020'`), the fix was
restored, and the full 41-test suite was re-confirmed passing.

The validator itself is tested the same way: three tests
(`test_validate_catches_a_deliberately_corrupted_target_row_count`,
`..._premium_checksum`, and `..._leaked_into_target`) deliberately
corrupt a correctly-migrated target database — deleting a row, altering
a premium value, and injecting a record that should have failed
validation — and confirm `validate_migration()` actually reports
failure in each case, rather than a validator that always says "OK."

## Project structure

```
schema-migration-accelerator/
├── src/
│   ├── legacy_schema.py   # synthetic legacy source schema + seed data
│   ├── target_schema.py   # normalized target schema
│   ├── transforms.py      # pure transform functions (name/date/premium)
│   ├── migrate.py         # dry-run + real migration pipeline
│   └── validate.py        # independent post-migration validation
├── tests/
│   ├── test_transforms.py
│   ├── test_migrate.py
│   └── test_validate.py
├── run_demo.py
├── requirements.txt
├── pytest.ini
└── .github/workflows/ci.yml
```

## What this project is not

- Not a real migration of any Allianz system or data — the legacy and
  target schemas, and all records in them, are synthetic, written to
  resemble a plausible policy-administration domain.
- Not built with a commercial ETL/migration platform (e.g. AWS DMS,
  Azure Data Migration) — this is a from-scratch Python accelerator,
  demonstrating the underlying migration-tooling skill (schema
  mapping, data-quality handling, dry-run planning, and independent
  validation) rather than platform-specific tooling experience.
- The legacy data's messiness (inconsistent formats, one corrupt
  value, one missing value) is deliberately designed to exercise real
  edge cases, not a claim about what any real legacy system looks
  like specifically.
