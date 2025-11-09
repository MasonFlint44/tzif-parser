import os.path
from datetime import datetime, timedelta, timezone

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

    def utc_to_local(self, dt: datetime) -> datetime:
        """
        Convert a UTC datetime to *naive* local wall time according to TZif data.
        - Accepts naive or aware datetimes. Naive is interpreted as UTC.
        - Returns a naive local datetime (no tzinfo), by design.
        """
        # Normalize to aware UTC
        dt_utc = (
            dt.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None
            else dt.astimezone(timezone.utc)
        )

        body = self.body

        # 0) No transitions at all => single ttinfo applies
        if not body.transitions:
            ttinfo = body.time_type_infos[0]
            return (dt_utc + timedelta(seconds=ttinfo.utc_offset_secs)).replace(
                tzinfo=None
            )

        first = body.transitions[0]
        last = body.transitions[-1]

        # 1) Before first transition: prefer a non-DST ttinfo if present
        if dt_utc < first.transition_time_utc:
            pre_tt = next(
                (tti for tti in body.time_type_infos if not tti.is_dst),
                body.time_type_infos[0],
            )
            return (dt_utc + timedelta(seconds=pre_tt.utc_offset_secs)).replace(
                tzinfo=None
            )

        # 2) Between transitions: use the transition's time type
        if dt_utc <= last.transition_time_utc:
            tr = body.find_transition(dt_utc)
            return (dt_utc + timedelta(seconds=tr.utc_offset_secs)).replace(tzinfo=None)

        # 3) After the last transition: apply POSIX footer rules if available
        if self._posix_tz_info is not None:
            footer = self.footer
            std_offset = footer.utc_offset_secs

            # POSIX rules compare in *naive local wall time*
            local_std_naive = (dt_utc + timedelta(seconds=std_offset)).replace(
                tzinfo=None
            )

            in_dst = False
            if footer.dst_start is not None and footer.dst_end is not None:
                start = footer.dst_start.to_datetime(local_std_naive.year)
                end = footer.dst_end.to_datetime(local_std_naive.year)

                if start < end:
                    in_dst = (local_std_naive >= start) and (local_std_naive < end)
                else:
                    # Southern hemisphere (wraps new year)
                    in_dst = (local_std_naive >= start) or (local_std_naive < end)

            # Default to +1h if footer has rules but no explicit dst offset
            if in_dst:
                offset_secs = (
                    footer.dst_offset_secs
                    if footer.dst_offset_secs is not None
                    else std_offset + 3600
                )
            else:
                offset_secs = std_offset

            return (dt_utc + timedelta(seconds=offset_secs)).replace(tzinfo=None)

        # 4) Fallback: no footer; use last known offset
        return (dt_utc + timedelta(seconds=last.utc_offset_secs)).replace(tzinfo=None)

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
