from datetime import datetime

import pytest

from tzif_parser.posix import PosixTzDateTime


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
def test_posix_tz_datetime_to_datetime(posix_datetime, year, expected):
    python_datetime = posix_datetime.to_datetime(year)
    assert python_datetime == expected
