import os.path
from dataclasses import dataclass

from .models import DstTransition, LeapSecondTransition
from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader


@dataclass
class TimeZoneInfo:
    timezone_name: str
    timezone_dir: str
    posix_tz_info: PosixTzInfo | None
    _header_data: TimeZoneInfoHeader | None
    _body_data: TimeZoneInfoBody | None
    _v2_header_data: TimeZoneInfoHeader | None = None
    _v2_body_data: TimeZoneInfoBody | None = None

    @property
    def version(self) -> int:
        return self.header.version

    @property
    def dst_transitions(self) -> list[DstTransition]:
        return self.body.dst_transitions

    @property
    def leap_second_transitions(self) -> list[LeapSecondTransition]:
        return self.body.leap_second_transitions

    @property
    def header(self) -> TimeZoneInfoHeader:
        if self._header_data is None:
            raise ValueError("No header data available")
        if self._header_data.version < 2:
            return self._header_data
        if self._v2_header_data is None:
            raise ValueError("No header data available")
        return self._v2_header_data

    @property
    def _body(self) -> TimeZoneInfoBody:
        if self._body_data is None:
            raise ValueError("No body data available")
        if self._header.version < 2:
            return self._body_data
        if self._v2_body_data is None:
            raise ValueError("No body data available")
        return self._v2_body_data

    @classmethod
    def read(cls, timezone_name: str):
        timezone_dir = os.environ.get("TZDIR") or "/usr/share/zoneinfo"
        filepath = cls.get_zoneinfo_filepath(timezone_name, timezone_dir)
        with open(filepath, "rb") as file:
            header_data = TimeZoneInfoHeader.read(file)
            body_data = TimeZoneInfoBody.read(file, header_data)
            if header_data.version < 2:
                return cls(timezone_name, timezone_dir, None, header_data, body_data)

            v2_header_data = TimeZoneInfoHeader.read(file)
            v2_body_data = TimeZoneInfoBody.read(
                file, v2_header_data, v2_header_data.version
            )
            v2_posix_string = PosixTzInfo.read(file)

            return cls(
                timezone_name,
                timezone_dir,
                v2_posix_string,
                header_data,
                body_data,
                v2_header_data,
                v2_body_data,
            )

    @classmethod
    def get_zoneinfo_filepath(cls, timezone_name: str, zoneinfo_dir: str) -> str:
        timezone_name_parts = timezone_name.partition("/")
        return os.path.join(
            zoneinfo_dir, timezone_name_parts[0], timezone_name_parts[2]
        )
