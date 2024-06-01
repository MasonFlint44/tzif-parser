import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO

from .models import LeapSecond, TTInfo
from .tzif_header import TimeZoneInfoHeader


# TODO: handle version 4 - first leap second can be neither -1 nor +1
# TODO: handle version 4 - if the last leap second transition matches the previous, the last entry represents the expiration of the leap second table rather than a leap second
@dataclass
class TimeZoneInfoBody:
    transition_times: tuple[datetime, ...]
    time_type_indices: list[int]
    ttinfo_entries: list[TTInfo]
    time_zone_abbrevs: list[str]
    leap_second_entries: list[LeapSecond]
    is_standard_flags: list[int]
    is_utc_flags: list[int]

    @classmethod
    def read(
        cls, file: IO[bytes], header_data: TimeZoneInfoHeader, version=1
    ) -> "TimeZoneInfoBody":
        # Parse transition times
        transition_times = cls._read_transition_times(
            file, header_data.transition_time_count, version
        )

        # Parse local time type indices
        time_type_indices = cls._read_time_type_indices(
            file, header_data.transition_time_count
        )

        # Parse ttinfo structures
        ttinfo_entries = cls._read_ttinfo_structures(
            file, header_data.local_time_type_count
        )

        # Parse time zone designation strings
        time_zone_abbrevs = cls._read_tz_designations(
            file, header_data.timezone_abbrev_byte_count
        )

        # Parse leap second data
        leap_second_entries = cls._read_leap_seconds(
            file, header_data.leap_second_count, version
        )

        # Parse standard/wall and UT/local indicators
        is_standard_flags = cls._read_indicators(
            file, header_data.is_standard_flag_count
        )
        is_utc_flags = cls._read_indicators(file, header_data.is_utc_flag_count)

        return TimeZoneInfoBody(
            transition_times,
            time_type_indices,
            ttinfo_entries,
            time_zone_abbrevs,
            leap_second_entries,
            is_standard_flags,
            is_utc_flags,
        )

    @classmethod
    def _read_transition_times(
        cls, file: IO[bytes], timecnt: int, version: int
    ) -> tuple[datetime, ...]:
        format_ = f">{timecnt}q" if version >= 2 else f">{timecnt}i"
        return tuple(
            datetime.fromtimestamp(transition, tz=UTC)
            for transition in struct.unpack(
                format_, file.read(8 * timecnt if version >= 2 else 4 * timecnt)
            )
        )

    @classmethod
    def _read_time_type_indices(cls, file: IO[bytes], timecnt: int) -> list[int]:
        return list(file.read(timecnt))

    @classmethod
    def _read_ttinfo_structures(cls, file: IO[bytes], typecnt: int) -> list[TTInfo]:
        ttinfo_format = (
            ">i?B"  # 4-byte signed integer, 1-byte boolean, 1-byte unsigned integer
        )
        ttinfo_size = struct.calcsize(ttinfo_format)
        ttinfo_structs = [
            struct.unpack(ttinfo_format, file.read(ttinfo_size)) for _ in range(typecnt)
        ]
        return [TTInfo(*ttinfo) for ttinfo in ttinfo_structs]

    @classmethod
    def _read_tz_designations(cls, file: IO[bytes], charcnt: int) -> list[str]:
        tz_string = file.read(charcnt).decode("ascii")
        return tz_string.split("\x00")

    @classmethod
    def _read_leap_seconds(
        cls, file: IO[bytes], count: int, version: int
    ) -> list[LeapSecond]:
        leap_format = f">{count}q" if version >= 2 else f">{count}i"
        leap_size = struct.calcsize(leap_format)
        leap_second_structs = [
            struct.unpack(leap_format, file.read(leap_size)) for _ in range(count)
        ]
        return [LeapSecond(*leap_second) for leap_second in leap_second_structs]

    @classmethod
    def _read_indicators(cls, file: IO[bytes], count: int) -> list[int]:
        return list(file.read(count))
