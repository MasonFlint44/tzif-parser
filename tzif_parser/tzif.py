import os.path
from datetime import datetime, timedelta

from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader


class TimeZoneInfo:
    def __init__(
        self,
        timezone_name: str,
        filepath: str,
        header_data: TimeZoneInfoHeader,
        body_data: TimeZoneInfoBody,
        v2_header_data: TimeZoneInfoHeader | None = None,
        v2_body_data: TimeZoneInfoBody | None = None,
        posix_tz_info: PosixTzInfo | None = None,
    ) -> None:
        self.timezone_name = timezone_name
        self.filepath = filepath
        self._posix_tz_info = posix_tz_info
        self._header_data = header_data
        self._body_data = body_data
        self._v2_header_data = v2_header_data
        self._v2_body_data = v2_body_data

    @property
    def version(self) -> int:
        return self.header.version

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
        if self.version < 2:
            return self._body_data
        if self._v2_body_data is None:
            raise ValueError("No body data available")
        return self._v2_body_data

    @property
    def footer(self) -> PosixTzInfo:
        if self._posix_tz_info is None:
            raise ValueError("No footer data available")
        return self._posix_tz_info

    def utc_to_local(self, dt) -> datetime:
        # Find the transition that is less than or equal to the given datetime
        transition = self.body.find_transition(dt)
        if transition == self.body.transitions[
            0
        ] and dt < transition.transition_time_utc.replace(tzinfo=None):
            # If the datetime is before the first transition, use the first ttinfo
            ttinfo = self.body.time_type_infos[0]
            utc_offset_secs = ttinfo.utc_offset_secs
        elif transition == self.body.transitions[
            -1
        ] and dt > transition.transition_time_utc.replace(tzinfo=None):
            # If the datetime is after the last transition, use the POSIX TZ info footer
            if self.footer.dst_start is None or self.footer.dst_end is None:
                # If the footer does not have DST start and end times, use the standard offset
                utc_offset_secs = self.footer.utc_offset_secs
            elif (
                self.footer.dst_start.to_datetime(dt.year)
                < dt
                < self.footer.dst_end.to_datetime(dt.year)
            ) and self.footer.dst_offset_secs is not None:
                # If the datetime is during DST, use the DST offset
                utc_offset_secs = self.footer.dst_offset_secs
            else:
                # Otherwise, use the standard offset
                utc_offset_secs = self.footer.utc_offset_secs
        else:
            # Otherwise, use the offset from the transition
            utc_offset_secs = transition.utc_offset_secs
        return dt + timedelta(seconds=utc_offset_secs)

    @classmethod
    def read(cls, timezone_name: str):
        timezone_dir = os.environ.get("TZDIR", "/usr/share/zoneinfo")
        filepath = cls.get_zoneinfo_filepath(timezone_name, timezone_dir)
        with open(filepath, "rb") as file:
            header_data = TimeZoneInfoHeader.read(file)
            body_data = TimeZoneInfoBody.read(file, header_data)
            if header_data.version < 2:
                return cls(timezone_name, filepath, header_data, body_data)

            v2_header_data = TimeZoneInfoHeader.read(file)
            v2_body_data = TimeZoneInfoBody.read(
                file, v2_header_data, v2_header_data.version
            )
            v2_posix_string = PosixTzInfo.read(file)

            return cls(
                timezone_name,
                filepath,
                header_data,
                body_data,
                v2_header_data,
                v2_body_data,
                v2_posix_string,
            )

    @classmethod
    def get_zoneinfo_filepath(cls, timezone_name: str, zoneinfo_dir: str) -> str:
        return os.path.join(zoneinfo_dir, *timezone_name.split("/"))

    def __repr__(self) -> str:
        return (
            f"TimeZoneInfo(timezone_name={self.timezone_name!r}, "
            f"filepath={self.filepath!r}, "
            f"header_data={self._header_data!r}, "
            f"body_data={self._body_data!r}, "
            f"v2_header_data={self._v2_header_data!r}, "
            f"v2_body_data={self._v2_body_data!r}, "
            f"posix_tz_info={self._posix_tz_info!r})"
        )
