import re
from datetime import time
from typing import IO

from .models import PosixTzDateTime


class PosixTzInfo:
    def __init__(self, file: IO[bytes]):
        self._file = file
        self._local_tz = None
        self._dst_start = None
        self._dst_end = None

    @property
    def local_tz(self):
        return self._local_tz

    @property
    def dst_start(self):
        return self._dst_start

    @property
    def dst_end(self):
        return self._dst_end

    def read(self):
        _ = self._file.readline()
        posix_string = self._file.readline().rstrip()
        local_tz, dst_start, dst_end = posix_string.split(b",")
        self._std_abbrev, self._utc_offset, self._dst_abbrev = re.split(
            b"(-?[0-9]+)", local_tz
        )
        self._dst_start = self._read_datetime(dst_start)
        self._dst_end = self._read_datetime(dst_end)

        return self

    # NOTE: calendar.monthdays2calendar should be able to help get a date for a week and weekday given a month
    def _read_datetime(self, posix_datetime: bytes) -> PosixTzDateTime:
        date_part, time_part = (
            posix_datetime.split(b"/")
            if b"/" in posix_datetime
            else (posix_datetime, b"00:00:00")
        )
        month, week, weekday = self._read_date(date_part)
        hour, minute, second = map(int, time_part.split(b":"))
        return PosixTzDateTime(month, week, weekday, time(hour, minute, second))

    def _read_date(self, posix_date: bytes) -> tuple[int, int, int]:
        month, week, weekday = posix_date.split(b".")
        return int(month[1:]), int(week), int(weekday)
