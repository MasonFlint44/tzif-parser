import os.path
import struct
from typing import IO, Any


class TZifParser:
    def __init__(self, tzname: str, zoneinfo_dir="/usr/share/zoneinfo"):
        self._tzname = tzname
        self._zoneinfo_dir = zoneinfo_dir

    def parse(self):
        filepath = self._get_zoneinfo_filepath()
        with open(filepath, "rb") as file:
            header_data = self._read_header(file)
            body_data = self._parse_body(file, header_data)
            if header_data["version"] >= 2:
                v2_header_data = self._read_header(file)
                v2_body_data = self._parse_body(
                    file, v2_header_data, header_data["version"]
                )
            pass

    def _read_header(self, file: IO[bytes]) -> dict[str, Any]:
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

        return {
            "version": int(version) if version != b"\x00" else 1,
            "tzh_ttisutcnt": tzh_ttisutcnt,
            "tzh_ttisstdcnt": tzh_ttisstdcnt,
            "tzh_leapcnt": tzh_leapcnt,
            "tzh_timecnt": tzh_timecnt,
            "tzh_typecnt": tzh_typecnt,
            "tzh_charcnt": tzh_charcnt,
        }

    def _get_zoneinfo_filepath(self) -> str:
        tzname_parts = self._tzname.partition("/")
        return os.path.join(self._zoneinfo_dir, tzname_parts[0], tzname_parts[2])

    def _parse_body(self, file: IO[bytes], header_data, version=1) -> dict[str, Any]:
        # Parse transition times
        transition_times = self._read_transition_times(
            file, header_data["tzh_timecnt"], version
        )

        # Parse local time type indices
        time_type_indices = self._read_time_type_indices(
            file, header_data["tzh_timecnt"]
        )

        # Parse ttinfo structures
        ttinfo_structures = self._read_ttinfo_structures(
            file, header_data["tzh_typecnt"]
        )

        # Parse time zone designation strings
        tz_designations = self._read_tz_designations(file, header_data["tzh_charcnt"])

        # Parse leap second data
        leap_seconds = self._read_leap_seconds(
            file, header_data["tzh_leapcnt"], version
        )

        # Parse standard/wall and UT/local indicators
        std_wall_indicators = self._read_indicators(file, header_data["tzh_ttisstdcnt"])
        ut_local_indicators = self._read_indicators(file, header_data["tzh_ttisutcnt"])

        return {
            "transition_times": transition_times,
            "time_type_indices": time_type_indices,
            "ttinfo_structures": ttinfo_structures,
            "tz_designations": tz_designations,
            "leap_seconds": leap_seconds,
            "std_wall_indicators": std_wall_indicators,
            "ut_local_indicators": ut_local_indicators,
        }

    def _read_transition_times(
        self, file: IO[bytes], timecnt: int, version: int
    ) -> tuple[int, ...]:
        format_ = f">{timecnt}q" if version >= 2 else f">{timecnt}i"
        return struct.unpack(
            format_, file.read(8 * timecnt if version >= 2 else 4 * timecnt)
        )

    def _read_time_type_indices(self, file: IO[bytes], timecnt: int) -> list[int]:
        return list(file.read(timecnt))

    def _read_ttinfo_structures(
        self, file: IO[bytes], typecnt: int
    ) -> list[tuple[int, bool, int]]:
        ttinfo_format = (
            ">i?B"  # 4-byte signed integer, 1-byte boolean, 1-byte unsigned integer
        )
        ttinfo_size = struct.calcsize(ttinfo_format)
        return [
            struct.unpack(ttinfo_format, file.read(ttinfo_size)) for _ in range(typecnt)
        ]  # type: ignore

    def _read_tz_designations(self, file: IO[bytes], charcnt: int) -> list[str]:
        tz_string = file.read(charcnt).decode("ascii")
        return tz_string.split("\x00")

    def _read_leap_seconds(
        self, file: IO[bytes], count: int, version: int
    ) -> list[tuple[int, ...]]:
        leap_format = f">{count}q" if version >= 2 else f">{count}i"
        leap_size = struct.calcsize(leap_format)
        return [struct.unpack(leap_format, file.read(leap_size)) for _ in range(count)]

    def _read_indicators(self, file: IO[bytes], count: int) -> list[int]:
        return list(file.read(count))


if __name__ == "__main__":
    parser = TZifParser("America/New_York")
    parser.parse()
