import os.path
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from .models import TimeZoneResolution
from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader

TimeZoneResolutionCache = namedtuple(
    "TimeZoneResolutionCache", ["resolution_time", "resolution"]
)


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
        self._last_resolution: TimeZoneResolutionCache | None = None

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

    def _cache_last_resolution(
        self, dt_utc: datetime, resolution: TimeZoneResolution
    ) -> TimeZoneResolution:
        self._last_resolution = TimeZoneResolutionCache(dt_utc, resolution)
        return resolution

    def resolve(self, dt: datetime) -> TimeZoneResolution:
        """
        Resolve this timezone at a given instant.
        Accepts naive (interpreted as UTC) or aware (converted to UTC).
        Returns a TimeZoneResolution with tz-aware UTC `resolution_time`
        and naive local wall `local_time`.
        """
        dt_utc = (
            dt.replace(tzinfo=timezone.utc)
            if dt.tzinfo is None
            else dt.astimezone(timezone.utc)
        )

        # Check cache
        if (
            self._last_resolution is not None
            and self._last_resolution.resolution_time == dt_utc
        ):
            return self._last_resolution.resolution

        body = self.body

        # Case 0: No transitions at all => single ttinfo applies
        if not body.transitions:
            tt = body.time_type_infos[0]
            std = next((x for x in body.time_type_infos if not x.is_dst), None)
            delta = (
                (tt.utc_offset_secs - std.utc_offset_secs) if (tt.is_dst and std) else 0
            )
            off = tt.utc_offset_secs
            abbr = body.get_abbrev_by_index(tt.abbrev_index)
            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name, dt_utc, local, off, tt.is_dst, abbr, delta
                ),
            )

        first = body.transitions[0]
        last = body.transitions[-1]

        # Case 1: Before first transition
        if dt_utc < first.transition_time_utc:
            tt = next(
                (x for x in body.time_type_infos if not x.is_dst),
                body.time_type_infos[0],
            )
            std = next((x for x in body.time_type_infos if not x.is_dst), None)
            delta = (
                (tt.utc_offset_secs - std.utc_offset_secs) if (tt.is_dst and std) else 0
            )
            off = tt.utc_offset_secs
            abbr = body.get_abbrev_by_index(tt.abbrev_index)
            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name, dt_utc, local, off, tt.is_dst, abbr, delta
                ),
            )

        # Case 2: Between transitions
        if dt_utc <= last.transition_time_utc:
            tr = body.find_transition(dt_utc)
            off = tr.utc_offset_secs
            delta = tr.dst_difference_secs if tr.is_dst else 0
            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    off,
                    tr.is_dst,
                    tr.abbreviation,
                    delta,
                ),
            )

        # Case 3: After the last transition, use POSIX footer if present
        if self._posix_tz_info is not None:
            f = self.footer
            std = f.utc_offset_secs

            # POSIX rules compare using *naive local wall time*
            local_std = (dt_utc + timedelta(seconds=std)).replace(tzinfo=None)
            in_dst = False
            if f.dst_start is not None and f.dst_end is not None:
                start = f.dst_start.to_datetime(local_std.year)
                end = f.dst_end.to_datetime(local_std.year)
                if start < end:
                    in_dst = start <= local_std < end
                else:
                    # wrap over new year (southern hemisphere rule)
                    in_dst = (local_std >= start) or (local_std < end)

            if in_dst:
                off = f.dst_offset_secs if f.dst_offset_secs is not None else std + 3600
                delta = (off - std) if f.dst_offset_secs is not None else 3600
                abbr = f.dst_abbrev or f.standard_abbrev
            else:
                off = std
                delta = 0
                abbr = f.standard_abbrev

            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name, dt_utc, local, off, in_dst, abbr, delta
                ),
            )

        # Case 4: No footer; stick to the last known offset
        off = last.utc_offset_secs
        delta = last.dst_difference_secs if last.is_dst else 0
        local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
        return self._cache_last_resolution(
            dt_utc,
            TimeZoneResolution(
                self.timezone_name,
                dt_utc,
                local,
                off,
                last.is_dst,
                last.abbreviation,
                delta,
            ),
        )

    def local(self, dt: datetime) -> datetime:
        """Naive local wall time at `dt`."""
        return self.resolve(dt).local_time

    def is_dst(self, dt: datetime) -> bool:
        return self.resolve(dt).is_dst

    def utc_offset_secs(self, dt: datetime) -> int:
        return self.resolve(dt).utc_offset_secs

    def dst_difference_secs(self, dt: datetime) -> int:
        return self.resolve(dt).dst_difference_secs

    def abbreviation(self, dt: datetime) -> str | None:
        return self.resolve(dt).abbreviation

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
