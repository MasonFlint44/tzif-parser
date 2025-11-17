import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import IO


@dataclass
class PosixTzJulianDateTime:
    day_of_year: int
    hour: int
    minute: int
    second: int

    def _is_leap_year(self, year: int) -> bool:
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    def to_datetime(self, year: int) -> datetime:
        # Jn excludes Feb 29. On leap years, days >= 60 are shifted by +1.
        base = datetime(year, 1, 1)
        day_index = self.day_of_year - 1
        if self._is_leap_year(year) and self.day_of_year >= 60:
            day_index += 1
        return base + timedelta(
            days=day_index, hours=self.hour, minutes=self.minute, seconds=self.second
        )


@dataclass
class PosixTzOrdinalDateTime:
    day_index: int  # 0..365 (includes Feb 29)
    hour: int
    minute: int
    second: int

    def to_datetime(self, year: int) -> datetime:
        base = datetime(year, 1, 1)
        return base + timedelta(
            days=self.day_index,
            hours=self.hour,
            minutes=self.minute,
            seconds=self.second,
        )


@dataclass
class PosixTzDateTime:
    month: int
    week: int  # 1..5 (5 = last)
    weekday: int  # POSIX: Sunday=0 ... Saturday=6
    hour: int
    minute: int
    second: int

    def to_datetime(self, year: int) -> datetime:
        # Convert POSIX weekday (Sun=0..Sat=6) to Python weekday (Mon=0..Sun=6)
        py_weekday = (self.weekday - 1) % 7  # Sun(0)->6, Mon(1)->0, ... Sat(6)->5

        # 1) Find first occurrence of py_weekday on/after the 1st of the month
        first_of_month = datetime(year, self.month, 1)
        first_wd = first_of_month.weekday()  # Mon=0..Sun=6
        delta = (py_weekday - first_wd) % 7
        first_occurrence = first_of_month + timedelta(days=delta)

        if self.week < 5:
            # 2) w-th occurrence (1-based): add 7*(w-1) days
            target = first_occurrence + timedelta(days=7 * (self.week - 1))
        else:
            # 3) Last occurrence: step to next month, back up to the last py_weekday
            if self.month == 12:
                next_month_first = datetime(year + 1, 1, 1)
            else:
                next_month_first = datetime(year, self.month + 1, 1)
            # last day of month
            last_of_month = next_month_first - timedelta(days=1)
            last_wd = last_of_month.weekday()
            back = (last_wd - py_weekday) % 7
            target = last_of_month - timedelta(days=back)

        return target.replace(
            hour=self.hour, minute=self.minute, second=self.second, microsecond=0
        )


@dataclass
class PosixTzInfo:
    posix_string: str
    standard_abbrev: str
    utc_offset_secs: int
    dst_abbrev: str | None
    dst_offset_secs: int | None
    dst_start: PosixTzDateTime | PosixTzJulianDateTime | PosixTzOrdinalDateTime | None
    dst_end: PosixTzDateTime | PosixTzJulianDateTime | PosixTzOrdinalDateTime | None

    @property
    def utc_offset_hours(self) -> float:
        return self.utc_offset_secs / 3600

    @property
    def dst_offset_hours(self) -> float | None:
        if self.dst_offset_secs is None:
            return None
        return self.dst_offset_secs / 3600

    @property
    def dst_difference_secs(self) -> int | None:
        if self.dst_offset_secs is None:
            return None
        return self.dst_offset_secs - self.utc_offset_secs

    @property
    def dst_difference_hours(self) -> float | None:
        if self.dst_difference_secs is None:
            return None
        return self.dst_difference_secs / 3600

    @classmethod
    def read(cls, file: IO[bytes]) -> "PosixTzInfo | None":
        # Adapted from zoneinfo._zoneinfo._parse_tz_str
        _ = file.readline()
        posix_line = file.readline()
        if posix_line == b"":
            return None

        posix_string = posix_line.rstrip(b"\n\x00")
        if not posix_string:
            return None

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
        if utc_offset is None:
            raise ValueError(f"{local_tz!r} is missing required standard offset")
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

        # POSIX constraints:
        # - hours 0..24 (not >24)
        # - minutes/seconds 0..59
        # - if hours == 24, then minutes == seconds == 0
        if h > 24:
            raise ValueError(f"Offset hours must be in [0, 24]: {posix_offset}")
        if not (0 <= m < 60 and 0 <= s < 60):
            raise ValueError(
                f"Offset minutes/seconds must be in [0, 59]: {posix_offset}"
            )
        if h == 24 and (m != 0 or s != 0):
            raise ValueError(f"24-hour offsets must be 24:00[:00]: {posix_offset}")

        total = h * 3600 + m * 60 + s
        # POSIX sign convention: positive means WEST of UTC => negative seconds
        if offset_match.group("sign") != "-":
            total = -total

        return total

    @classmethod
    def _read_dst_transition_datetime(
        cls, posix_datetime: str
    ) -> PosixTzDateTime | PosixTzJulianDateTime | PosixTzOrdinalDateTime | None:
        date, *time = posix_datetime.split("/", 1)
        t = time[0] if time else None
        trans_time = cls._read_dst_transition_time(t) if t else (2, 0, 0)

        if not date:
            return None

        if date.startswith("M"):
            m = re.fullmatch(r"M(\d{1,2})\.(\d)\.(\d)", date)
            if m is None:
                raise ValueError(f"Invalid dst start/end date: {posix_datetime}")
            month, week, weekday = (int(x) for x in m.groups())
            if not (1 <= month <= 12 and 1 <= week <= 5 and 0 <= weekday <= 6):
                raise ValueError(f"Invalid M<m>.<w>.<d>: {posix_datetime}")
            return PosixTzDateTime(month, week, weekday, *trans_time)

        if date.startswith("J"):
            n = int(date[1:])
            if not (1 <= n <= 365):
                raise ValueError(f"J<n> must be 1..365: {posix_datetime}")
            return PosixTzJulianDateTime(n, *trans_time)

        # Plain numeric day-of-year (0..365), includes Feb 29
        if date.isdigit():
            n = int(date)
            if not (0 <= n <= 365):
                raise ValueError(f"<n> must be 0..365: {posix_datetime}")
            return PosixTzOrdinalDateTime(n, *trans_time)

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

        # bounds: hours 0..167, minutes/seconds 0..59
        if h > 167:
            raise ValueError(f"Hour must be in [0, 167]: {time_str}")
        if not (0 <= m < 60 and 0 <= s < 60):
            raise ValueError(f"Minutes/seconds must be in [0, 59]: {time_str}")

        if match.group("sign") == "-":
            h, m, s = -h, -m, -s

        return h, m, s
