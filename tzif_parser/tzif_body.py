import struct
from datetime import datetime
from typing import IO

from .dst_transition import DstTransition
from .models import LeapSecondTransition, WallStandardFlag
from .ttinfo import TimeTypeInfo
from .tzif_header import TimeZoneInfoHeader


# TODO: handle version 4 - first leap second can be neither -1 nor +1
# TODO: handle version 4 - if the last leap second transition matches the previous, the last entry represents the expiration of the leap second table rather than a leap second
class TimeZoneInfoBody:
    def __init__(
        self,
        dst_transitions,
        leap_second_transitions,
        time_type_info,
        time_type_indices,
        timezone_abbrevs,
    ) -> None:
        self.dst_transitions = dst_transitions
        self.leap_second_transitions = leap_second_transitions
        self._time_type_info = time_type_info
        self._time_type_indices = time_type_indices
        self._timezone_abbrevs = timezone_abbrevs

    @property
    def timezone_abbrevs(self) -> list[str]:
        return self._timezone_abbrevs.split("\x00")

    @classmethod
    def read(
        cls, file: IO[bytes], header_data: TimeZoneInfoHeader, version=1
    ) -> "TimeZoneInfoBody":
        # Parse transition times
        dst_transition_times = cls._read_transition_times(
            file, header_data.dst_transitions_count, version
        )

        # Parse local time type indices
        time_type_indices = cls._read_time_type_indices(
            file, header_data.dst_transitions_count
        )

        # Parse ttinfo structures
        time_type_info = cls._read_ttinfo_structures(
            file, header_data.local_time_type_count
        )

        dst_transitions = [
            DstTransition(
                transition_time=dst_transition_time,
                time_type_info=time_type_info[time_type_index],
                prev_time_type_info=(
                    time_type_info[time_type_indices[transition_index - 1]]
                    if transition_index > 0
                    and time_type_info[time_type_index].is_wall_standard
                    == WallStandardFlag.WALL
                    else None
                ),
            )
            for transition_index, (dst_transition_time, time_type_index) in enumerate(
                zip(dst_transition_times, time_type_indices)
            )
        ]

        # Parse time zone designation strings
        timezone_abbrevs = cls._read_tz_designations(
            file, header_data.timezone_abbrev_byte_count
        )

        # Set abbreviations on ttinfo structures
        for ttinfo in time_type_info:
            ttinfo.timezone_abbrevs = timezone_abbrevs

        # Parse leap second data
        leap_second_transitions = cls._read_leap_seconds(
            file, header_data.leap_second_transitions_count, version
        )

        # Parse standard/wall and UT/local indicators
        is_standard_flags = cls._read_indicators(
            file, header_data.wall_standard_flag_count
        )
        is_utc_flags = cls._read_indicators(file, header_data.is_utc_flag_count)

        # Set standard/wall indicators on ttinfo structures
        for transition_index in range(header_data.wall_standard_flag_count):
            time_type_info[transition_index].is_wall_standard = WallStandardFlag(
                is_standard_flags[transition_index]
            )

        # Set UTC/local indicators on ttinfo structures
        for transition_index in range(header_data.is_utc_flag_count):
            time_type_info[transition_index].is_utc = bool(
                is_utc_flags[transition_index]
            )

        return TimeZoneInfoBody(
            dst_transitions,
            leap_second_transitions,
            time_type_info,
            time_type_indices,
            timezone_abbrevs,
        )

    @classmethod
    def _read_transition_times(
        cls, file: IO[bytes], timecnt: int, version: int
    ) -> list[datetime]:
        format_ = f">{timecnt}q" if version >= 2 else f">{timecnt}i"
        return [
            datetime.fromtimestamp(transition)
            for transition in struct.unpack(
                format_, file.read(8 * timecnt if version >= 2 else 4 * timecnt)
            )
        ]

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
    ) -> list[LeapSecondTransition]:
        leap_format = f">{count}q" if version >= 2 else f">{count}i"
        leap_size = struct.calcsize(leap_format)
        leap_second_structs = []
        for _ in range(count):
            leap_second_struct = struct.unpack(leap_format, file.read(leap_size))
            leap_second_structs.append(LeapSecondTransition(*leap_second_struct))
        return leap_second_structs

    @classmethod
    def _read_indicators(cls, file: IO[bytes], count: int) -> list[int]:
        return list(file.read(count))
