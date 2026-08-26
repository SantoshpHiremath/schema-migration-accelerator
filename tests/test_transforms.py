"""
tests/test_transforms.py
---------------------------

Tests the pure transform functions directly, covering every legacy
format variant present in the sample data plus the error paths.
"""

from __future__ import annotations

import pytest

from src.transforms import (
    TransformError,
    normalize_contact,
    normalize_date,
    normalize_name,
    normalize_premium_to_cents,
)


class TestNormalizeName:
    def test_comma_format_is_reordered_to_first_last(self):
        assert normalize_name("Mueller, Anna") == "Anna Mueller"

    def test_lowercase_no_comma_is_title_cased(self):
        assert normalize_name("schmidt thomas") == "Schmidt Thomas"

    def test_uppercase_no_comma_is_title_cased(self):
        assert normalize_name("WEBER MAX") == "Weber Max"

    def test_none_raises(self):
        with pytest.raises(TransformError):
            normalize_name(None)

    def test_empty_string_raises(self):
        with pytest.raises(TransformError):
            normalize_name("   ")

    def test_single_word_raises(self):
        with pytest.raises(TransformError):
            normalize_name("Cher")

    def test_comma_with_empty_side_raises(self):
        with pytest.raises(TransformError):
            normalize_name("Mueller,")


class TestNormalizeDate:
    def test_already_iso_passes_through(self):
        assert normalize_date("2021-03-14") == "2021-03-14"

    def test_dot_format_dmy(self):
        assert normalize_date("14.06.2020") == "2020-06-14"

    def test_slash_format_mdy(self):
        assert normalize_date("01/09/2019") == "2019-01-09"

    def test_dash_format_dmy(self):
        assert normalize_date("19-07-2021") == "2021-07-19"

    def test_none_raises(self):
        with pytest.raises(TransformError):
            normalize_date(None)

    def test_unrecognized_format_raises(self):
        with pytest.raises(TransformError):
            normalize_date("March 14, 2021")

    def test_out_of_range_month_raises(self):
        with pytest.raises(TransformError):
            normalize_date("13.13.2021")


class TestNormalizePremiumToCents:
    def test_two_decimal_places(self):
        assert normalize_premium_to_cents("482.50") == 48250

    def test_whole_number_no_decimal(self):
        assert normalize_premium_to_cents("2200.00") == 220000

    def test_one_decimal_place_is_padded(self):
        assert normalize_premium_to_cents("100.5") == 10050

    def test_no_decimal_at_all(self):
        assert normalize_premium_to_cents("500") == 50000

    def test_empty_string_raises(self):
        with pytest.raises(TransformError):
            normalize_premium_to_cents("")

    def test_none_raises(self):
        with pytest.raises(TransformError):
            normalize_premium_to_cents(None)

    def test_non_numeric_value_raises(self):
        """This is the exact corrupt case in the sample legacy data
        (record 10: 'not_a_number') -- must be caught, not silently
        coerced to 0, since that would be a silent data-loss bug in a
        financial field."""
        with pytest.raises(TransformError):
            normalize_premium_to_cents("not_a_number")

    def test_negative_number_raises(self):
        with pytest.raises(TransformError):
            normalize_premium_to_cents("-50.00")


class TestNormalizeContact:
    def test_full_contact_normalizes_all_fields(self):
        contact = normalize_contact("Mueller, Anna", "Anna.Mueller@Example.com", "+49 151 1234567")
        assert contact.full_name == "Anna Mueller"
        assert contact.email == "anna.mueller@example.com"
        assert contact.phone == "+491511234567"

    def test_missing_email_becomes_none_not_error(self):
        """A missing email shouldn't block migration -- only a missing
        name should, since email is optional in the target schema."""
        contact = normalize_contact("Fischer, Lea", None, "+49 160 5551234")
        assert contact.email is None
        assert contact.full_name == "Lea Fischer"

    def test_missing_phone_becomes_none_not_error(self):
        contact = normalize_contact("Hoffmann, Ben", "ben.hoffmann@example.com", None)
        assert contact.phone is None

    def test_missing_name_raises_even_if_email_and_phone_present(self):
        with pytest.raises(TransformError):
            normalize_contact(None, "someone@example.com", "+49 151 0000000")

    def test_phone_with_dashes_and_spaces_is_normalized(self):
        contact = normalize_contact("Becker, Julia", "julia.becker@example.com", "0160-1112233")
        assert contact.phone == "01601112233"
