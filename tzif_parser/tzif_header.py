import struct
from dataclasses import dataclass
from typing import IO


@dataclass
class TimeZoneInfoHeader:
    version: int
    tzh_ttisutcnt: int
    tzh_ttisstdcnt: int
    tzh_leapcnt: int
    tzh_timecnt: int
    tzh_typecnt: int
    tzh_charcnt: int

    @classmethod
    def read(cls, file: IO[bytes]) -> "TimeZoneInfoHeader":
        format_ = ">4s1c15x6I"  # Big endian, 4 bytes, 1 byte, skip 15 bytes, 6 unsigned integers
        header_size = struct.calcsize(format_)
        header_data = struct.unpack(format_, file.read(header_size))
        (
            magic,
            version,
            tzh_ttisutcnt,
            tzh_ttisstdcnt,
            tzh_leapcnt,
            tzh_timecnt,
            tzh_typecnt,
            tzh_charcnt,
        ) = header_data

        if magic != b"TZif":
            raise ValueError("Invalid TZif file: Magic sequence not found.")

        return cls(
            int(version) if version != b"\x00" else 1,
            tzh_ttisutcnt,
            tzh_ttisstdcnt,
            tzh_leapcnt,
            tzh_timecnt,
            tzh_typecnt,
            tzh_charcnt,
        )
