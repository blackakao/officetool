from datetime import date, datetime

import pytest

from excel_data_sort.birthdate import normalize_birthdate


@pytest.mark.parametrize("value,expected", [
    ("62-01-01", "1962-01-01"), ("620101", "1962-01-01"),
    ("19620101", "1962-01-01"), (19620101, "1962-01-01"),
    (19620101.0, "1962-01-01"), ("1962.1.1", "1962-01-01"),
    ("1962/01/01", "1962-01-01"), ("1962년 1월 1일", "1962-01-01"),
    (" 1962 1 1 ", "1962-01-01"), ("１９６２．１．１", "1962-01-01"),
    ("1962-01-01 00:00:00", "1962-01-01"),
    (date(1962, 1, 1), "1962-01-01"), (datetime(1962, 1, 1, 12), "1962-01-01"),
    ("000229", "2000-02-29"), ("26-12-31", "2026-12-31"),
    ("27-01-01", "1927-01-01"), (None, None), ("", ""),
])
def test_birthdate_formats(value, expected):
    assert normalize_birthdate(value, current_year=2026) == expected


def test_birthdate_century_and_explicit_year():
    assert normalize_birthdate("26-01-01", "1900", 2026) == "1926-01-01"
    assert normalize_birthdate("27-01-01", current_year=2027) == "2027-01-01"
    assert normalize_birthdate("1920-01-01", current_year=2026) == "1920-01-01"
    assert normalize_birthdate("2020-01-01", "1900", 2026) == "2020-01-01"


@pytest.mark.parametrize("value", ["19620230", "1900.2.29", "62-13-01", "01/31/1962", "unknown", True, 45000, "1962", "19620101 extra"])
def test_invalid_birthdates_are_not_guessed(value):
    with pytest.raises(ValueError):
        normalize_birthdate(value, current_year=2026)
