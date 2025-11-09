import struct
from dataclasses import dataclass
from typing import IO


@dataclass
class TimeZoneInfoHeader:
    version: int
    is_utc_flag_count: int
    wall_standard_flag_count: int
    leap_second_transitions_count: int
    transitions_count: int
    local_time_type_count: int
    timezone_abbrev_byte_count: int

    @classmethod
    def read(cls, file: IO[bytes]) -> "TimeZoneInfoHeader":
        format_ = ">4s1c15x6I"
        header_size = struct.calcsize(format_)
        header_data = struct.unpack(format_, file.read(header_size))
        (
            magic,
            version_byte,
            is_utc_flag_count,
            wall_standard_flag_count,
            leap_second_count,
            transitions_count,
            local_time_type_count,
            timezone_abbrev_byte_count,
        ) = header_data

        if magic != b"TZif":
            raise ValueError("Invalid TZif file: Magic sequence not found.")

        version = 1 if version_byte == b"\x00" else int(version_byte.decode("ascii"))

        return cls(
            version,
            is_utc_flag_count,
            wall_standard_flag_count,
            leap_second_count,
            transitions_count,
            local_time_type_count,
            timezone_abbrev_byte_count,
        )
