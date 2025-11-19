import bisect
import struct
from datetime import datetime, timedelta, timezone
from typing import IO

from .models import LeapSecondTransition, TimeTypeInfo
from .tz_transition import TimeZoneTransition
from .tzif_header import TimeZoneInfoHeader

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class TimeZoneInfoBody:
    def __init__(
        self,
        transition_times: list[datetime],
        leap_second_transitions: list[LeapSecondTransition],
        time_type_infos: list[TimeTypeInfo],
        time_type_indices: list[int],
        timezone_abbrevs: str,
        wall_standard_flags: list[int],
        is_utc_flags: list[int],
        leap_second_expiration: datetime | None = None,
    ) -> None:
        self.transition_times = transition_times
        self.leap_second_transitions = leap_second_transitions
        self.time_type_infos = time_type_infos
        self.time_type_indices = time_type_indices
        self._timezone_abbrevs = timezone_abbrevs
        self.wall_standard_flags = wall_standard_flags
        self.is_utc_flags = is_utc_flags
        self.leap_second_expiration = leap_second_expiration
        self.transitions = [
            TimeZoneTransition(
                transition_time,
                self.time_type_infos,
                self.time_type_indices,
                transition_index,
                self.wall_standard_flags,
                self.is_utc_flags,
                self._timezone_abbrevs,
            )
            for transition_index, transition_time in enumerate(self.transition_times)
        ]

    @property
    def timezone_abbrevs(self) -> list[str]:
        seen: list[str] = []
        for ttinfo in self.time_type_infos:
            abbr = self.get_abbrev_by_index(ttinfo.abbrev_index)
            if abbr not in seen:
                seen.append(abbr)
        return seen

    def get_abbrev_by_index(self, index: int) -> str:
        if index < 0 or index >= len(self._timezone_abbrevs):
            raise IndexError("Index out of range")
        return self._timezone_abbrevs[index:].partition("\x00")[0]

    def find_transition_index(self, dt: datetime) -> int | None:
        # Find the index of the transition time that is less than or equal to the given datetime
        dt = (
            dt.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None
            else dt.astimezone(timezone.utc)
        )
        index = bisect.bisect_right(self.transition_times, dt)
        if index == 0:
            return None
        return index - 1

    def find_leap_second_index(self, dt: datetime) -> int | None:
        dt = (
            dt.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None
            else dt.astimezone(timezone.utc)
        )
        timestamps = [
            _EPOCH + timedelta(seconds=ls.transition_time)
            for ls in self.leap_second_transitions
        ]
        index = bisect.bisect_right(timestamps, dt)
        if index == 0:
            return None
        return index - 1

    @classmethod
    def read(
        cls, file: IO[bytes], header_data: TimeZoneInfoHeader, version=1
    ) -> "TimeZoneInfoBody":
        # Parse transition times
        dst_transitions = cls._read_transition_times(
            file, header_data.transitions_count, version
        )

        # Parse local time type indices
        time_type_indices = cls._read_time_type_indices(
            file, header_data.transitions_count
        )

        # Parse ttinfo structures
        time_type_info = cls._read_ttinfo_structures(
            file, header_data.local_time_type_count
        )

        # Parse time zone designation strings
        timezone_abbrevs = cls._read_tz_designations(
            file, header_data.timezone_abbrev_byte_count
        )

        # Parse leap second data
        (
            leap_second_transitions,
            leap_second_expiration,
        ) = cls._read_leap_seconds(
            file, header_data.leap_second_transitions_count, version
        )

        # Parse standard/wall and UT/local indicators
        wall_standard_flags = cls._read_indicators(
            file, header_data.wall_standard_flag_count
        )
        is_utc_flags = cls._read_indicators(file, header_data.is_utc_flag_count)

        return TimeZoneInfoBody(
            dst_transitions,
            leap_second_transitions,
            time_type_info,
            time_type_indices,
            timezone_abbrevs,
            wall_standard_flags,
            is_utc_flags,
            leap_second_expiration=leap_second_expiration,
        )

    @classmethod
    def _read_transition_times(
        cls, file: IO[bytes], timecnt: int, version: int
    ) -> list[datetime]:
        fmt = f">{timecnt}q" if version >= 2 else f">{timecnt}i"
        raw = struct.unpack(fmt, file.read((8 if version >= 2 else 4) * timecnt))
        return [_EPOCH + timedelta(seconds=t) for t in raw]

    @classmethod
    def _read_time_type_indices(cls, file: IO[bytes], timecnt: int) -> list[int]:
        return list(file.read(timecnt))

    @classmethod
    def _read_ttinfo_structures(
        cls, file: IO[bytes], typecnt: int
    ) -> list[TimeTypeInfo]:
        ttinfo_format = (
            ">i?B"  # 4-byte signed integer, 1-byte boolean, 1-byte unsigned integer
        )
        ttinfo_size = struct.calcsize(ttinfo_format)
        return [
            TimeTypeInfo(*struct.unpack(ttinfo_format, file.read(ttinfo_size)))
            for _ in range(typecnt)
        ]

    @classmethod
    def _read_tz_designations(cls, file: IO[bytes], charcnt: int) -> str:
        return file.read(charcnt).decode("ascii")

    @classmethod
    def _read_leap_seconds(
        cls, file: IO[bytes], count: int, version: int
    ) -> tuple[list[LeapSecondTransition], datetime | None]:
        # Each leap-second entry is a pair: (transition_time, correction)
        if count == 0:
            return [], None

        fmt = ">qi" if version >= 2 else ">ii"
        size = struct.calcsize(fmt)
        leaps = [
            LeapSecondTransition(*struct.unpack(fmt, file.read(size)))
            for _ in range(count)
        ]

        expiration: datetime | None = None
        if version >= 4 and len(leaps) >= 2:
            last = leaps[-1]
            previous = leaps[-2]
            if last.transition_time == previous.transition_time:
                last.is_expiration = True
                expiration = _EPOCH + timedelta(seconds=last.transition_time)

        return leaps, expiration

    @classmethod
    def _read_indicators(cls, file: IO[bytes], count: int) -> list[int]:
        return list(file.read(count))

    def __repr__(self) -> str:
        return (
            f"TimeZoneInfoBody(transition_times={self.transition_times!r}, "
            f"leap_second_transitions={self.leap_second_transitions!r}, "
            f"leap_second_expiration={self.leap_second_expiration!r}, "
            f"time_type_infos={self.time_type_infos!r}, "
            f"time_type_indices={self.time_type_indices!r}, "
            f"timezone_abbrevs={self._timezone_abbrevs!r}, "
            f"wall_standard_flags={self.wall_standard_flags!r}, "
            f"is_utc_flags={self.is_utc_flags!r})"
        )
