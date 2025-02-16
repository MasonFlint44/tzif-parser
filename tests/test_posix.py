from tzif_parser.posix import PosixTzDateTime


def test_posix_tz_datetime_to_datetime_case_1():
    posix_datetime = PosixTzDateTime(6, 1, 1, 0, 0, 0)
    python_datetime = posix_datetime.to_datetime(2025)

    assert python_datetime.year == 2025
    assert python_datetime.month == 6
    assert python_datetime.day == 2
    assert python_datetime.hour == 0
    assert python_datetime.minute == 0
    assert python_datetime.second == 0


def test_posix_tz_datetime_to_datetime_case_2():
    posix_datetime = PosixTzDateTime(1, 1, 0, 0, 0, 0)
    python_datetime = posix_datetime.to_datetime(2025)

    assert python_datetime.year == 2025
    assert python_datetime.month == 1
    assert python_datetime.day == 5
    assert python_datetime.hour == 0
    assert python_datetime.minute == 0
    assert python_datetime.second == 0
