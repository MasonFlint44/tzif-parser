import struct
from dataclasses import dataclass
from typing import IO

from .tzif_header import TimeZoneInfoHeader


@dataclass
class TimeZoneInfoBody:
    transition_times: tuple[int, ...]
    time_type_indices: list[int]
    ttinfo_structures: list[tuple[int, bool, int]]
    tz_designations: list[str]
    leap_seconds: list[tuple[int, ...]]
    std_wall_indicators: list[int]
    ut_local_indicators: list[int]

    @classmethod
    def read(
        cls, file: IO[bytes], header_data: TimeZoneInfoHeader, version=1
    ) -> "TimeZoneInfoBody":
        # Parse transition times
        transition_times = cls._read_transition_times(
            file, header_data.tzh_timecnt, version
        )

        # Parse local time type indices
        time_type_indices = cls._read_time_type_indices(file, header_data.tzh_timecnt)

        # Parse ttinfo structures
        ttinfo_structures = cls._read_ttinfo_structures(file, header_data.tzh_typecnt)

        # Parse time zone designation strings
        tz_designations = cls._read_tz_designations(file, header_data.tzh_charcnt)

        # Parse leap second data
        leap_seconds = cls._read_leap_seconds(file, header_data.tzh_leapcnt, version)

        # Parse standard/wall and UT/local indicators
        std_wall_indicators = cls._read_indicators(file, header_data.tzh_ttisstdcnt)
        ut_local_indicators = cls._read_indicators(file, header_data.tzh_ttisutcnt)

        return TimeZoneInfoBody(
            transition_times,
            time_type_indices,
            ttinfo_structures,
            tz_designations,
            leap_seconds,
            std_wall_indicators,
            ut_local_indicators,
        )

    @classmethod
    def _read_transition_times(
        cls, file: IO[bytes], timecnt: int, version: int
    ) -> tuple[int, ...]:
        format_ = f">{timecnt}q" if version >= 2 else f">{timecnt}i"
        return struct.unpack(
            format_, file.read(8 * timecnt if version >= 2 else 4 * timecnt)
        )

    @classmethod
    def _read_time_type_indices(cls, file: IO[bytes], timecnt: int) -> list[int]:
        return list(file.read(timecnt))

    @classmethod
    def _read_ttinfo_structures(
        cls, file: IO[bytes], typecnt: int
    ) -> list[tuple[int, bool, int]]:
        ttinfo_format = (
            ">i?B"  # 4-byte signed integer, 1-byte boolean, 1-byte unsigned integer
        )
        ttinfo_size = struct.calcsize(ttinfo_format)
        return [
            struct.unpack(ttinfo_format, file.read(ttinfo_size)) for _ in range(typecnt)
        ]  # type: ignore

    @classmethod
    def _read_tz_designations(cls, file: IO[bytes], charcnt: int) -> list[str]:
        tz_string = file.read(charcnt).decode("ascii")
        return tz_string.split("\x00")

    @classmethod
    def _read_leap_seconds(
        cls, file: IO[bytes], count: int, version: int
    ) -> list[tuple[int, ...]]:
        leap_format = f">{count}q" if version >= 2 else f">{count}i"
        leap_size = struct.calcsize(leap_format)
        return [struct.unpack(leap_format, file.read(leap_size)) for _ in range(count)]

    @classmethod
    def _read_indicators(cls, file: IO[bytes], count: int) -> list[int]:
        return list(file.read(count))
