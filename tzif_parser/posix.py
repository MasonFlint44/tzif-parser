import re
from calendar import Calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
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
class PosixTzJulianDateTime:
    day_of_year: int
    hour: int
    minute: int
    second: int

    def to_datetime(self, year: int) -> datetime:
        return datetime(
            year,
            1,
            1,
            self.hour,
            self.minute,
            self.second,
        ) + timedelta(days=self.day_of_year - 1)


@dataclass
class PosixTzDateTime:
    month: int
    week: int
    weekday: int
    hour: int
    minute: int
    second: int

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
            self.hour,
            self.minute,
            self.second,
        )


@dataclass
class PosixTzInfo:
    posix_string: str
    standard_abbrev: str
    utc_offset_secs: int
    dst_abbrev: str | None
    dst_offset_secs: int | None
    dst_start: PosixTzDateTime | PosixTzJulianDateTime | None
    dst_end: PosixTzDateTime | PosixTzJulianDateTime | None

    @property
    def utc_offset_hours(self) -> float:
        return self.utc_offset_secs / 3600

    @property
    def dst_offset_hours(self) -> float | None:
        return self.dst_offset_secs / 3600 if self.dst_offset_secs is not None else None

    @classmethod
    def read(cls, file: IO[bytes]) -> "PosixTzInfo":
        # Adapted from zoneinfo._zoneinfo._parse_tz_str
        _ = file.readline()
        posix_string = file.readline().rstrip()
        local_tz, dst_start, dst_end = (
            posix_string.split(b",")
            if b"," in posix_string
            else (posix_string, b"", b"")
        )

        local_tz_parser = re.compile(
            r"""
            (?P<std>[^<0-9:.+-]+|<[a-zA-Z0-9+-]+>)
            (?:
                (?P<stdoff>[+-]?\d{1,3}(?::\d{2}(?::\d{2})?)?)
                (?:
                    (?P<dst>[^0-9:.+-]+|<[a-zA-Z0-9+-]+>)
                    (?P<dstoff>[+-]?\d{1,3}(?::\d{2}(?::\d{2})?)?)?
                )? # dst
            )? # stdoff
            """,
            re.ASCII | re.VERBOSE,
        )
        local_tz_match = local_tz_parser.fullmatch(local_tz.decode("utf-8"))
        if local_tz_match is None:
            raise ValueError(f"{local_tz} is not a valid TZ string")

        standard_abbrev = local_tz_match.group("std").strip("<>")
        utc_offset = local_tz_match.group("stdoff")
        utc_offset_secs = cls._read_offset(utc_offset)
        dst_abbrev = local_tz_match.group("dst")
        if dst_abbrev:
            dst_abbrev = dst_abbrev.strip("<>")
        dst_offset = local_tz_match.group("dstoff")
        if dst_offset:
            dst_offset_secs = cls._read_offset(dst_offset)
        elif dst_abbrev:
            dst_offset_secs = utc_offset_secs + 3600
        else:
            dst_offset_secs = None
        posix_string = posix_string.decode("utf-8")
        dst_start = cls._read_dst_transition_datetime(dst_start.decode("utf-8"))
        dst_end = cls._read_dst_transition_datetime(dst_end.decode("utf-8"))

        return cls(
            posix_string,
            standard_abbrev,
            utc_offset_secs,
            dst_abbrev,
            dst_offset_secs,
            dst_start,
            dst_end,
        )

    @classmethod
    def _read_offset(cls, posix_offset: str) -> int:
        # Adapted from zoneinfo._zoneinfo._parse_tz_delta
        offset_parser = re.compile(
            r"(?P<sign>[+-])?(?P<h>\d{1,3})(:(?P<m>\d{2})(:(?P<s>\d{2}))?)?",
            re.ASCII,
        )
        offset_match = offset_parser.fullmatch(posix_offset)
        if offset_match is None:
            raise ValueError(f"{posix_offset} is not a valid offset")
        h, m, s = (int(v or 0) for v in offset_match.group("h", "m", "s"))
        total = h * 3600 + m * 60 + s
        if h > 24:
            raise ValueError(f"Offset hours must be in [0, 24]: {posix_offset}")
        if offset_match.group("sign") != "-":
            total = -total
        return total

    @classmethod
    def _read_dst_transition_datetime(
        cls, posix_datetime: str
    ) -> PosixTzDateTime | PosixTzJulianDateTime | None:
        # Adapted from zoneinfo._zoneinfo._parse_dst_start_end
        date, *time = posix_datetime.split("/", 1)
        type_ = date[:1]
        if type_ == "M":
            datetime_parser = re.compile(r"M(\d{1,2})\.(\d).(\d)", re.ASCII)
            datetime_match = datetime_parser.fullmatch(date)
            if datetime_match is None:
                raise ValueError(f"Invalid dst start/end date: {posix_datetime}")
            date_offset = tuple(map(int, datetime_match.groups()))
            transition_time = (
                cls._read_dst_transition_time(time[0]) if len(time) > 0 else (2, 0, 0)
            )
            return PosixTzDateTime(
                date_offset[0], date_offset[1], date_offset[2], *transition_time
            )
        if type_ == "J":
            date = date[1:]
            day_of_year = int(date)
            transition_time = (
                cls._read_dst_transition_time(time[0]) if len(time) > 0 else (2, 0, 0)
            )
            return PosixTzJulianDateTime(day_of_year, *transition_time)
        return None

    @classmethod
    def _read_dst_transition_time(cls, time_str):
        # Adapted from zoneinfo._zoneinfo._parse_transition_time
        transition_time_parser = re.compile(
            r"(?P<sign>[+-])?(?P<h>\d{1,3})(:(?P<m>\d{2})(:(?P<s>\d{2}))?)?",
            re.ASCII,
        )
        match = transition_time_parser.fullmatch(time_str)
        if match is None:
            raise ValueError(f"Invalid time: {time_str}")

        h, m, s = (int(v or 0) for v in match.group("h", "m", "s"))

        if h > 167:
            raise ValueError(f"Hour must be in [0, 167]: {time_str}")

        if match.group("sign") == "-":
            h, m, s = -h, -m, -s

        return h, m, s
