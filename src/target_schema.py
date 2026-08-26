"""
target_schema.py
-------------------

Defines the "target" system: a normalized SQLite schema splitting the
legacy flat table into `customers`, `addresses`, and `policies` --
the shape a modern system typically wants (avoid repeating a
customer's name/email/phone on every policy row).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

TARGET_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    UNIQUE(full_name, email)
);

CREATE TABLE IF NOT EXISTS addresses (
    address_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    line1 TEXT,
    city TEXT,
    country_code TEXT
);

CREATE TABLE IF NOT EXISTS policies (
    policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    policy_number TEXT UNIQUE NOT NULL,
    policy_type TEXT,
    premium_amount_cents INTEGER,
    signup_date TEXT,  -- normalized to ISO 8601 (YYYY-MM-DD)
    source_legacy_record_id INTEGER NOT NULL
);
"""


def create_target_db(db_path: str | Path, drop_existing: bool = True) -> Path:
    db_path = Path(db_path)
    conn = sqlite3.connect(db_path)
    try:
        if drop_existing:
            conn.execute("DROP TABLE IF EXISTS policies")
            conn.execute("DROP TABLE IF EXISTS addresses")
            conn.execute("DROP TABLE IF EXISTS customers")
        conn.executescript(TARGET_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    return db_path
