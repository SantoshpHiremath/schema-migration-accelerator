"""
transforms.py
---------------

Pure, independently-testable transform functions used by the migration
pipeline. Kept separate from the pipeline orchestration (migrate.py) so
each transform's edge cases can be tested directly, not just through an
end-to-end migration run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class TransformError(Exception):
    """Raised when a legacy field cannot be safely transformed. The
    pipeline catches these per-record so one bad row doesn't abort an
    entire migration batch."""


def normalize_name(raw_name: str | None) -> str:
    """Normalizes legacy name formats into 'First Last'.

    Handles two real formats seen in the sample data:
      - "Last, First"  -> "First Last"
      - "first last" / "FIRST LAST" (no comma) -> title-cased as-is

    Raises TransformError on None/empty, since a customer record
    without a name is not safely migratable.
    """
    if not raw_name or not raw_name.strip():
        raise TransformError("name is missing or empty")

    raw_name = raw_name.strip()

    if "," in raw_name:
        last, _, first = raw_name.partition(",")
        last = last.strip().title()
        first = first.strip().title()
        if not first or not last:
            raise TransformError(f"could not split comma-formatted name: {raw_name!r}")
        return f"{first} {last}"

    # No comma: assume "First Last" order already, just normalize case.
    parts = raw_name.split()
    if len(parts) < 2:
        raise TransformError(f"name has fewer than 2 parts: {raw_name!r}")
    return " ".join(p.title() for p in parts)


_DATE_FORMATS = [
    # (regex, group order) -> (year, month, day)
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "ymd"),        # 2021-03-14 (already ISO)
    (re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$"), "dmy_dot"),  # 14.06.2020
    (re.compile(r"^(\d{2})/(\d{2})/(\d{4})$"), "mdy_slash"),  # 01/09/2019 (US-style, as stored)
    (re.compile(r"^(\d{2})-(\d{2})-(\d{4})$"), "dmy_dash"),   # 19-07-2021
]


def normalize_date(raw_date: str | None) -> str:
    """Normalizes any of the legacy system's inconsistent date formats
    into ISO 8601 (YYYY-MM-DD). Raises TransformError for anything
    unrecognized rather than guessing at an ambiguous format."""
    if not raw_date or not raw_date.strip():
        raise TransformError("signup_date is missing or empty")

    raw_date = raw_date.strip()

    for pattern, fmt in _DATE_FORMATS:
        m = pattern.match(raw_date)
        if not m:
            continue
        if fmt == "ymd":
            year, month, day = m.groups()
        elif fmt == "dmy_dot":
            day, month, year = m.groups()
        elif fmt == "mdy_slash":
            month, day, year = m.groups()
        elif fmt == "dmy_dash":
            day, month, year = m.groups()
        else:  # pragma: no cover - defensive, unreachable given _DATE_FORMATS above
            raise TransformError(f"unhandled date format tag: {fmt}")

        year_i, month_i, day_i = int(year), int(month), int(day)
        if not (1 <= month_i <= 12) or not (1 <= day_i <= 31):
            raise TransformError(f"date has out-of-range month/day: {raw_date!r}")
        return f"{year_i:04d}-{month_i:02d}-{day_i:02d}"

    raise TransformError(f"unrecognized date format: {raw_date!r}")


def normalize_premium_to_cents(raw_premium: str | None) -> int:
    """Converts a legacy premium string (e.g. '482.50') into an integer
    number of cents, avoiding float rounding issues. Raises
    TransformError for missing or non-numeric values rather than
    silently coercing to 0, which would be a silent data-loss bug."""
    if raw_premium is None or raw_premium.strip() == "":
        raise TransformError("premium_amount is missing or empty")

    raw_premium = raw_premium.strip()

    if not re.match(r"^\d+(\.\d{1,2})?$", raw_premium):
        raise TransformError(f"premium_amount is not a valid decimal number: {raw_premium!r}")

    if "." in raw_premium:
        whole, frac = raw_premium.split(".")
        frac = (frac + "00")[:2]
    else:
        whole, frac = raw_premium, "00"

    return int(whole) * 100 + int(frac)


@dataclass(frozen=True)
class NormalizedContact:
    full_name: str
    email: str | None
    phone: str | None


def normalize_contact(cust_name: str | None, cust_email: str | None, cust_phone: str | None) -> NormalizedContact:
    """Normalizes the contact fields together (name is required and can
    raise; email/phone are optional and simply normalized to None if
    blank, since a missing phone number shouldn't block a migration the
    way a missing name should)."""
    full_name = normalize_name(cust_name)
    email = cust_email.strip().lower() if cust_email and cust_email.strip() else None
    phone = _normalize_phone(cust_phone)
    return NormalizedContact(full_name=full_name, email=email, phone=phone)


def _normalize_phone(raw_phone: str | None) -> str | None:
    if not raw_phone or not raw_phone.strip():
        return None
    # Strip spaces and hyphens; keep the leading + if present.
    digits = re.sub(r"[^\d+]", "", raw_phone.strip())
    return digits or None
