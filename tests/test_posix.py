from datetime import datetime

import pytest

from tzif_parser.posix import (
    PosixTzDateTime,
    PosixTzInfo,
    PosixTzJulianDateTime,
    PosixTzOrdinalDateTime,
)


@pytest.mark.parametrize(
    "posix_datetime, year, expected",
    [
        (PosixTzDateTime(6, 1, 1, 0, 0, 0), 2025, datetime(2025, 6, 2, 0, 0, 0)),
        (PosixTzDateTime(1, 1, 0, 0, 0, 0), 2025, datetime(2025, 1, 5, 0, 0, 0)),
        (PosixTzDateTime(3, 2, 0, 2, 0, 0), 2025, datetime(2025, 3, 9, 2, 0, 0)),
        (PosixTzDateTime(11, 1, 0, 2, 0, 0), 2025, datetime(2025, 11, 2, 2, 0, 0)),
        (PosixTzDateTime(3, 2, 0, 2, 0, 0), 2026, datetime(2026, 3, 8, 2, 0, 0)),
        (PosixTzDateTime(11, 1, 0, 2, 0, 0), 2026, datetime(2026, 11, 1, 2, 0, 0)),
    ],
)
def test_posix_tz_datetime_to_datetime(posix_datetime: PosixTzDateTime, year, expected):
    python_datetime = posix_datetime.to_datetime(year)
    assert python_datetime == expected


@pytest.mark.parametrize(
    "posix_dt, year, expected",
    [
        # First Monday of Feb 2025 -> 2025-02-03
        (PosixTzDateTime(2, 1, 1, 0, 0, 0), 2025, datetime(2025, 2, 3, 0, 0, 0)),
        # Last Sunday of Oct 2025 (w=5 means "last") -> 2025-10-26
        (PosixTzDateTime(10, 5, 0, 0, 0, 0), 2025, datetime(2025, 10, 26, 0, 0, 0)),
        # Last Monday of May 2025 -> 2025-05-26
        (PosixTzDateTime(5, 5, 1, 0, 0, 0), 2025, datetime(2025, 5, 26, 0, 0, 0)),
        # Hour/min/sec honored
        (
            PosixTzDateTime(7, 1, 2, 6, 30, 15),
            2025,
            datetime(2025, 7, 1, 6, 30, 15),
        ),  # first Tue of July 2025 is the 1st
    ],
)
def test_posix_tz_datetime_to_datetime_more(posix_dt, year, expected):
    assert posix_dt.to_datetime(year) == expected


# -------------------------
# J<n> (Julian without Feb 29) semantics
# -------------------------


@pytest.mark.parametrize(
    "j, year, expected",
    [
        # J60 -> Mar 1 both in leap and non-leap years (because J excludes Feb 29)
        (
            PosixTzJulianDateTime(60, 0, 0, 0),
            2024,
            datetime(2024, 3, 1, 0, 0, 0),
        ),  # leap year
        (
            PosixTzJulianDateTime(60, 0, 0, 0),
            2023,
            datetime(2023, 3, 1, 0, 0, 0),
        ),  # non-leap year
        # J365 -> Dec 31 (works for both leap and non-leap years)
        (
            PosixTzJulianDateTime(365, 23, 59, 59),
            2024,
            datetime(2024, 12, 31, 23, 59, 59),
        ),
        (PosixTzJulianDateTime(365, 0, 0, 0), 2023, datetime(2023, 12, 31, 0, 0, 0)),
    ],
)
def test_posix_julian_datetime(j, year, expected):
    assert j.to_datetime(year) == expected


# -------------------------
# Plain ordinal <n> (0..365, includes Feb 29)
# -------------------------


@pytest.mark.parametrize(
    "o, year, expected",
    [
        # In leap year: day_index 59 -> Feb 29
        (PosixTzOrdinalDateTime(59, 0, 0, 0), 2024, datetime(2024, 2, 29, 0, 0, 0)),
        # In non-leap: day_index 59 -> Mar 1
        (PosixTzOrdinalDateTime(59, 0, 0, 0), 2023, datetime(2023, 3, 1, 0, 0, 0)),
        # Boundaries
        (PosixTzOrdinalDateTime(0, 12, 34, 56), 2025, datetime(2025, 1, 1, 12, 34, 56)),
        (PosixTzOrdinalDateTime(365, 0, 0, 0), 2024, datetime(2024, 12, 31, 0, 0, 0)),
    ],
)
def test_posix_ordinal_datetime(o, year, expected):
    assert o.to_datetime(year) == expected


# -------------------------
# Transition time parsing (± and up to 167 hours)
# -------------------------


@pytest.mark.parametrize(
    "time_str, expected",
    [
        ("2", (2, 0, 0)),
        ("2:30", (2, 30, 0)),
        ("2:30:15", (2, 30, 15)),
        ("167", (167, 0, 0)),  # max allowed hours
        (
            "-1:30:15",
            (-1, -30, -15),
        ),  # negative applies to all components in our implementation
    ],
)
def test_read_dst_transition_time(time_str, expected):
    assert PosixTzInfo._read_dst_transition_time(time_str) == expected


@pytest.mark.parametrize("bad", ["168", "200:00", "00:60", "00:59:60"])
def test_read_dst_transition_time_invalid(bad):
    with pytest.raises(ValueError):
        PosixTzInfo._read_dst_transition_time(bad)


# -------------------------
# Offset parsing (POSIX sign rules)
# -------------------------


@pytest.mark.parametrize(
    "offset_str, seconds",
    [
        ("5", -5 * 3600),  # POSIX: stdoff with no sign means WEST of UTC (negative)
        ("+5", -5 * 3600),  # '+' also means west (negative)
        ("-02:30", 2 * 3600 + 30 * 60),
        ("14", -14 * 3600),
        ("00:45:30", -(45 * 60 + 30)),  # 00:45:30 west of UTC
    ],
)
def test_read_offset(offset_str, seconds):
    assert PosixTzInfo._read_offset(offset_str) == seconds


@pytest.mark.parametrize("bad", ["25", "99:00", "24:60", "24:00:60", "abc"])
def test_read_offset_invalid(bad):
    with pytest.raises(ValueError):
        PosixTzInfo._read_offset(bad)


# -------------------------
# Date form parser: M / J / <n>
# -------------------------


@pytest.mark.parametrize(
    "expr, expected_type, expected_tuple",
    [
        ("M3.2.0/2", PosixTzDateTime, (3, 2, 0, 2, 0, 0)),
        ("J60/2", PosixTzJulianDateTime, (60, 2, 0, 0)),
        ("60/2", PosixTzOrdinalDateTime, (60, 2, 0, 0)),
        ("", type(None), None),
    ],
)
def test_read_dst_transition_datetime(expr, expected_type, expected_tuple):
    obj = PosixTzInfo._read_dst_transition_datetime(expr)
    if expected_type is type(None):
        assert obj is None
    else:
        assert isinstance(obj, expected_type)
        assert tuple(obj.__dict__.values()) == expected_tuple


@pytest.mark.parametrize(
    "bad", ["M13.1.0", "M0.1.0", "M5.6.0", "M5.1.7", "J0", "J366", "367"]
)
def test_read_dst_transition_datetime_invalid(bad):
    with pytest.raises(ValueError):
        PosixTzInfo._read_dst_transition_datetime(bad)
