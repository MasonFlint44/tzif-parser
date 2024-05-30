import re
from calendar import Calendar
from dataclasses import dataclass
from datetime import datetime
from datetime import time as dt_time
from typing import IO

posix_weekdays_to_python = {
    0: 6,
    1: 0,
    2: 1,
    3: 2,
    4: 3,
    5: 4,
    6: 5,
}


@dataclass
class PosixTzDateTime:
    month: int
    week: int
    weekday: int
    time: dt_time

    def __init__(self, month: int, week: int, weekday: int, time: dt_time):
        self._calendar = Calendar()
        self.month = month
        self.week = week
        self.weekday = weekday
        self.time = time

    def to_datetime(self, year: int) -> datetime:
        weeks = self._calendar.monthdays2calendar(year, self.month)
        week = weeks[self.week - 1 if self.week < 5 else -1]
        day = next(
            day for day in week if day[1] == posix_weekdays_to_python[self.weekday]
        )
        return datetime(
            year,
            self.month,
            day[0],
            self.time.hour,
            self.time.minute,
            self.time.second,
        )


@dataclass
class PosixTzInfo:
    std_abbrev: str
    utc_offset: int
    dst_abbrev: str
    dst_start: PosixTzDateTime
    dst_end: PosixTzDateTime

    def __init__(
        self,
        std_abbrev: str,
        utc_offset: int,
        dst_abbrev: str,
        dst_start: PosixTzDateTime,
        dst_end: PosixTzDateTime,
    ):
        self._calendar = Calendar()
        self.std_abbrev: str = std_abbrev
        self.utc_offset: int = utc_offset
        self.dst_abbrev: str = dst_abbrev
        self.dst_start: PosixTzDateTime = dst_start
        self.dst_end: PosixTzDateTime = dst_end

    @classmethod
    def read(cls, file: IO[bytes]) -> "PosixTzInfo":
        _ = file.readline()
        posix_string = file.readline().rstrip()
        local_tz, dst_start, dst_end = posix_string.split(b",")
        std_abbrev, utc_offset, dst_abbrev = re.split(b"(-?[0-9]+)", local_tz)
        std_abbrev = std_abbrev.decode("utf-8")
        dst_abbrev = dst_abbrev.decode("utf-8")
        utc_offset = int(utc_offset.decode("utf-8"))
        dst_start = cls._read_datetime(dst_start)
        dst_end = cls._read_datetime(dst_end)

        return cls(
            std_abbrev,
            utc_offset,
            dst_abbrev,
            dst_start,
            dst_end,
        )

    @classmethod
    def _read_datetime(cls, posix_datetime: bytes) -> PosixTzDateTime:
        date_part, time_part = (
            posix_datetime.split(b"/")
            if b"/" in posix_datetime
            else (posix_datetime, b"02:00:00")
        )
        month, week, weekday = cls._read_date(date_part)
        hour, minute, second = map(int, time_part.split(b":"))
        return PosixTzDateTime(month, week, weekday, dt_time(hour, minute, second))

    @staticmethod
    def _read_date(posix_date: bytes) -> tuple[int, int, int]:
        month, week, weekday = posix_date.split(b".")
        return int(month[1:]), int(week), int(weekday)
