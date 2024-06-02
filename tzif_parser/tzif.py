import os.path
from dataclasses import dataclass

from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader


# TODO: is there an environment variable that can be used to determine the zoneinfo directory?
@dataclass
class TimeZoneInfo:
    timezone_name: str
    zoneinfo_dir: str
    posix_string: PosixTzInfo | None
    _header_data: TimeZoneInfoHeader | None
    _body_data: TimeZoneInfoBody | None
    _v2_header_data: TimeZoneInfoHeader | None = None
    _v2_body_data: TimeZoneInfoBody | None = None

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
    def body(self) -> TimeZoneInfoBody:
        if self._body_data is None:
            raise ValueError("No body data available")
        if self.header.version < 2:
            return self._body_data
        if self._v2_body_data is None:
            raise ValueError("No body data available")
        return self._v2_body_data

    @classmethod
    def read(cls, timezone_name: str, zoneinfo_dir: str = "/usr/share/zoneinfo"):
        filepath = cls.get_zoneinfo_filepath(timezone_name, zoneinfo_dir)
        with open(filepath, "rb") as file:
            header_data = TimeZoneInfoHeader.read(file)
            body_data = TimeZoneInfoBody.read(file, header_data)
            if header_data.version < 2:
                return cls(timezone_name, zoneinfo_dir, None, header_data, body_data)

            v2_header_data = TimeZoneInfoHeader.read(file)
            v2_body_data = TimeZoneInfoBody.read(
                file, v2_header_data, v2_header_data.version
            )
            v2_posix_string = PosixTzInfo.read(file)

            return cls(
                timezone_name,
                zoneinfo_dir,
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
