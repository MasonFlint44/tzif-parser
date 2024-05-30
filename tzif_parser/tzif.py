import os.path

from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader


class TimeZoneInfo:
    def __init__(self, tzname: str, zoneinfo_dir="/usr/share/zoneinfo"):
        self._tzname = tzname
        self._zoneinfo_dir = zoneinfo_dir
        self._header_data = None
        self._body_data = None
        self._v2_header_data = None
        self._v2_body_data = None
        self._v2_posix_string = None

    def read(self):
        filepath = self._get_zoneinfo_filepath()
        with open(filepath, "rb") as file:
            self._header_data = TimeZoneInfoHeader.read(file)
            self._body_data = TimeZoneInfoBody.read(file, self._header_data)
            if self._header_data.version >= 2:
                self._v2_header_data = TimeZoneInfoHeader.read(file)
                self._v2_body_data = TimeZoneInfoBody.read(
                    file, self._v2_header_data, self._v2_header_data.version
                )
                self._v2_posix_string = PosixTzInfo.read(file)

        return self

    def _get_zoneinfo_filepath(self) -> str:
        tzname_parts = self._tzname.partition("/")
        return os.path.join(self._zoneinfo_dir, tzname_parts[0], tzname_parts[2])
