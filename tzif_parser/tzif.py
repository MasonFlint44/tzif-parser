import os.path
from dataclasses import dataclass

from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader


@dataclass
class TimeZoneInfo:
    timezone_name: str
    zoneinfo_dir: str = "/usr/share/zoneinfo"
    header_data: TimeZoneInfoHeader | None = None
    body_data: TimeZoneInfoBody | None = None
    v2_header_data: TimeZoneInfoHeader | None = None
    v2_body_data: TimeZoneInfoBody | None = None
    v2_posix_string: PosixTzInfo | None = None

    def read(self):
        filepath = self._get_zoneinfo_filepath()
        with open(filepath, "rb") as file:
            self.header_data = TimeZoneInfoHeader.read(file)
            self.body_data = TimeZoneInfoBody.read(file, self.header_data)

            if self.header_data.version >= 2:
                self.v2_header_data = TimeZoneInfoHeader.read(file)
                self.v2_body_data = TimeZoneInfoBody.read(
                    file, self.v2_header_data, self.v2_header_data.version
                )
                self.v2_posix_string = PosixTzInfo.read(file)

        return self

    def _get_zoneinfo_filepath(self) -> str:
        timezone_name_parts = self.timezone_name.partition("/")
        return os.path.join(
            self.zoneinfo_dir, timezone_name_parts[0], timezone_name_parts[2]
        )
