import struct
from dataclasses import dataclass
from typing import IO


@dataclass
class TimeZoneInfoHeader:
    version: int
    is_utc_flag_count: int
    is_standard_flag_count: int
    leap_second_count: int
    transition_time_count: int
    local_time_type_count: int
    timezone_abbrev_byte_count: int

    @classmethod
    def read(cls, file: IO[bytes]) -> "TimeZoneInfoHeader":
        format_ = ">4s1c15x6I"  # Big endian, 4 bytes, 1 byte, skip 15 bytes, 6 unsigned integers
        header_size = struct.calcsize(format_)
        header_data = struct.unpack(format_, file.read(header_size))
        (
            magic,
            version,
            is_utc_flag_count,
            is_standard_flag_count,
            leap_second_count,
            transition_time_count,
            local_time_type_count,
            timezone_abbrev_byte_count,
        ) = header_data

        if magic != b"TZif":
            raise ValueError("Invalid TZif file: Magic sequence not found.")

        return cls(
            int(version) if version != b"\x00" else 1,
            is_utc_flag_count,
            is_standard_flag_count,
            leap_second_count,
            transition_time_count,
            local_time_type_count,
            timezone_abbrev_byte_count,
        )
