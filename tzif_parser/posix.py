import re
from calendar import Calendar
from datetime import datetime, time
from typing import IO

from .models import PosixTzDateTime

posix_weekdays_to_python = {
    0: 6,
    1: 0,
    2: 1,
    3: 2,
    4: 3,
    5: 4,
    6: 5,
}


class PosixTzInfo:
    def __init__(self, file: IO[bytes]):
        self._calendar = Calendar()
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

    def get_dst_start(self, year: int) -> datetime:
        if not self._dst_start:
            raise ValueError("DST start not set")
        return self._get_date_time(year, self._dst_start)

    def get_dst_end(self, year: int) -> datetime:
        if not self._dst_end:
            raise ValueError("DST end not set")
        return self._get_date_time(year, self._dst_end)

    def _get_date_time(self, year: int, posix_datetime: PosixTzDateTime) -> datetime:
        if posix_datetime.week == 5:
            days = [
                day
                for day in self._calendar.itermonthdays2(2044, posix_datetime.month)
                if day[0] != 0
            ]
            # Find the last day of the month that matches the weekday
            day = next(
                day
                for day in reversed(days)
                if day[1] == posix_weekdays_to_python[posix_datetime.weekday]
            )
            return datetime(
                year,
                posix_datetime.month,
                day[0],
                posix_datetime.time.hour,
                posix_datetime.time.minute,
                posix_datetime.time.second,
            )
        # TODO: what if the first thursday isn't in the first week of the month?
        # TODO: what if second thursday isn't in the second week of the month?
        weeks = self._calendar.monthdays2calendar(year, posix_datetime.month)
        week = weeks[posix_datetime.week - 1]
        day = next(
            day
            for day in week
            if day[1] == posix_weekdays_to_python[posix_datetime.weekday]
        )
        return datetime(
            year,
            posix_datetime.month,
            day[0],
            posix_datetime.time.hour,
            posix_datetime.time.minute,
            posix_datetime.time.second,
        )

    def read(self) -> "PosixTzInfo":
        _ = self._file.readline()
        posix_string = self._file.readline().rstrip()
        local_tz, dst_start, dst_end = posix_string.split(b",")
        self._std_abbrev, self._utc_offset, self._dst_abbrev = re.split(
            b"(-?[0-9]+)", local_tz
        )
        self._dst_start = self._read_datetime(dst_start)
        self._dst_end = self._read_datetime(dst_end)

        return self

    # TODO: what should the default time be?
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
