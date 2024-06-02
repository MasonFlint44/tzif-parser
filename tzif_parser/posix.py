import re
from calendar import Calendar
from dataclasses import dataclass
from datetime import datetime
from datetime import time as time_
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
_calendar = Calendar()


@dataclass
class PosixTzDateTime:
    month: int
    week: int
    weekday: int
    time: time_

    def to_datetime(self, year: int) -> datetime:
        weeks = _calendar.monthdays2calendar(year, self.month)
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


# TODO: handle version 3 - hours is -167 through 167
# TODO: handle version 3 - make dst all year if it starts jan 1 at 00:00 and ends dec 31 at 24:00 plus difference between dst and std
@dataclass
class PosixTzInfo:
    standard_abbrev: str
    utc_offset_hours: int
    dst_abbrev: str | None
    dst_start: PosixTzDateTime | None
    dst_end: PosixTzDateTime | None

    @classmethod
    def read(cls, file: IO[bytes]) -> "PosixTzInfo":
        _ = file.readline()
        posix_string = file.readline().rstrip()
        local_tz, dst_start, dst_end = (
            posix_string.split(b",")
            if b"," in posix_string
            else (posix_string, b"", b"")
        )
        standard_abbrev, utc_offset_hours, dst_abbrev = re.split(
            b"(-?[0-9]+)", local_tz
        )
        standard_abbrev = standard_abbrev.decode("utf-8")
        dst_abbrev = dst_abbrev.decode("utf-8") if len(dst_abbrev) > 0 else None
        utc_offset_hours = int(utc_offset_hours.decode("utf-8"))
        dst_start = cls._read_datetime(dst_start)
        dst_end = cls._read_datetime(dst_end)

        return cls(
            standard_abbrev,
            utc_offset_hours,
            dst_abbrev,
            dst_start,
            dst_end,
        )

    @classmethod
    def _read_datetime(cls, posix_datetime: bytes) -> PosixTzDateTime | None:
        if len(posix_datetime) == 0:
            return None
        date_part, time_part = (
            posix_datetime.split(b"/")
            if b"/" in posix_datetime
            else (posix_datetime, b"02:00:00")
        )
        month, week, weekday = cls._read_date(date_part)
        hour, minute, second = map(int, time_part.split(b":"))
        return PosixTzDateTime(month, week, weekday, time_(hour, minute, second))

    @staticmethod
    def _read_date(posix_date: bytes) -> tuple[int, int, int]:
        month, week, weekday = posix_date.split(b".")
        return int(month[1:]), int(week), int(weekday)
