"""
legacy_schema.py
------------------

Defines and seeds a synthetic "legacy" source system: a single flat,
denormalized SQLite table modeled on how an older policy-administration
or customer system often actually looks in practice -- one wide table,
inconsistent casing, some nulls, some duplicate customer names with
different formatting. This is the "before" side of the migration this
project demonstrates.

All data is synthetic, generated here, not sourced from any real
company or system.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

LEGACY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS legacy_customer_records (
    record_id INTEGER PRIMARY KEY,
    cust_name TEXT,
    cust_email TEXT,
    cust_phone TEXT,
    addr_line TEXT,
    city TEXT,
    country_code TEXT,
    policy_number TEXT,
    policy_type TEXT,
    premium_amount TEXT,   -- stored as TEXT in the legacy system, deliberately
    signup_date TEXT       -- inconsistent date formats, deliberately
);
"""

SAMPLE_RECORDS = [
    # (record_id, cust_name, cust_email, cust_phone, addr_line, city, country_code, policy_number, policy_type, premium_amount, signup_date)
    (1, "Mueller, Anna", "anna.mueller@example.com", "+49 151 1234567", "Hauptstr. 12", "Munich", "DE", "POL-1001", "auto", "482.50", "2021-03-14"),
    (2, "schmidt thomas", "t.schmidt@example.com", "0176-9988771", "Bahnhofallee 5", "Berlin", "DE", "POL-1002", "home", "1290.00", "14.06.2020"),
    (3, "Fischer, Lea", None, "+49 160 5551234", "Ringstr. 88", "Hamburg", "DE", "POL-1003", "auto", "615.75", "2022-11-01"),
    (4, "WEBER MAX", "max.weber@example.com", "+49 172 4443322", "Gartenweg 3", "Cologne", "DE", "POL-1004", "life", "2200.00", "01/09/2019"),
    (5, "Meyer, Sofia", "sofia.meyer@example.com", "0151-7776655", "Lindenallee 21", "Munich", "DE", "POL-1005", "home", "", "2023-02-28"),  # missing premium
    (6, "Wagner, Paul", "paul.wagner@example.com", "+49 152 3332211", "Ahornstr. 9", "Frankfurt", "DE", "POL-1006", "auto", "530.00", "2021-07-19"),
    (7, "becker julia", "julia.becker@example.com", "0160-1112233", "Am Wald 4", "Stuttgart", "DE", "POL-1007", "home", "980.20", "19-07-2021"),
    (8, "Hoffmann, Ben", "ben.hoffmann@example.com", None, "Bergstr. 17", "Munich", "DE", "POL-1008", "life", "1750.00", "2020-12-05"),
    (9, "Mueller, Anna", "anna.mueller@example.com", "+49 151 1234567", "Hauptstr. 12", "Munich", "DE", "POL-1009", "life", "3100.00", "2023-05-30"),  # same customer, second policy
    (10, "Klein, Nora", "nora.klein@example.com", "+49 157 8887766", "Seestr. 60", "Hamburg", "DE", "POL-1010", "auto", "not_a_number", "2022-01-15"),  # corrupt value
]


def create_and_seed_legacy_db(db_path: str | Path) -> Path:
    """Creates the legacy SQLite database and seeds it with sample
    records. Idempotent: safe to call against an existing file, tables
    are dropped and recreated so re-runs are deterministic."""
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS legacy_customer_records")
        conn.execute(LEGACY_SCHEMA_SQL)
        conn.executemany(
            "INSERT INTO legacy_customer_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            SAMPLE_RECORDS,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path
