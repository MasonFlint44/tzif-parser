import os
import sysconfig
from collections import namedtuple
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from importlib import resources
from typing import IO

from .models import TimeZoneResolution
from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader

TimeZoneResolutionCache = namedtuple(
    "TimeZoneResolutionCache", ["cache_key", "resolution"]
)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


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
    def footer(self) -> PosixTzInfo | None:
        return self._posix_tz_info

    def _cache_last_resolution(
        self, cache_key: datetime, resolution: TimeZoneResolution
    ) -> TimeZoneResolution:
        self._last_resolution = TimeZoneResolutionCache(cache_key, resolution)
        return resolution

    @staticmethod
    def _initial_tt_state(
        body: TimeZoneInfoBody,
    ) -> tuple[int, int, str | None, bool]:
        """
        Pick the standard ttinfo if present (otherwise the first ttinfo) and
        return its offset, dst delta, abbreviation, and dst flag.
        """
        std = next((x for x in body.time_type_infos if not x.is_dst), None)
        tt = std if std is not None else body.time_type_infos[0]
        delta = (
            (tt.utc_offset_secs - std.utc_offset_secs) if (tt.is_dst and std) else 0
        )
        abbr = body.get_abbrev_by_index(tt.abbrev_index)
        return tt.utc_offset_secs, delta, abbr, tt.is_dst

    @staticmethod
    def _posix_offsets(posix_info: PosixTzInfo) -> tuple[int, int, int]:
        """
        Return (standard offset, dst offset, dst delta) in seconds
        derived from a PosixTzInfo footer.
        """
        std = posix_info.utc_offset_secs
        dst_offset = (
            posix_info.dst_offset_secs
            if posix_info.dst_offset_secs is not None
            else std + 3600
        )
        return std, dst_offset, dst_offset - std

    def _posix_footer_state(
        self, dt_utc: datetime
    ) -> tuple[int, int, str | None, bool] | None:
        f = self.footer
        if f is None:
            return None

        std, dst_offset, dst_delta = self._posix_offsets(f)

        # POSIX rules compare using naive local wall time in standard offset
        local_std = (dt_utc + timedelta(seconds=std)).replace(tzinfo=None)
        in_dst = False
        if f.dst_start is not None and f.dst_end is not None:
            start = f.dst_start.to_datetime(local_std.year)
            end = f.dst_end.to_datetime(local_std.year) - timedelta(seconds=dst_delta)
            if start < end:
                in_dst = start <= local_std < end
            else:
                # wrap over new year (southern hemisphere rule)
                in_dst = (local_std >= start) or (local_std < end)

        if in_dst:
            off = dst_offset
            delta = dst_delta
            abbr = f.dst_abbrev or f.standard_abbrev
        else:
            off = std
            delta = 0
            abbr = f.standard_abbrev

        return off, delta, abbr, in_dst

    def _next_posix_transition_utc(self, dt_utc: datetime) -> datetime | None:
        """
        Compute the next transition instant in UTC using the POSIX footer rules,
        for a given UTC datetime strictly after the end of the TZif transition body.

        Returns a timezone-aware UTC datetime, or None if no DST rules exist.
        """
        f = self.footer
        if f is None:
            return None
        if f.dst_start is None or f.dst_end is None:
            return None

        std, dst_offset, dst_delta = self._posix_offsets(f)
        dst_delta_td = timedelta(seconds=dst_delta)

        # Work in "standard-time local wall clock" coordinates, same as resolve()
        std_delta = timedelta(seconds=std)
        local_std = (dt_utc + std_delta).replace(tzinfo=None)
        year = local_std.year

        candidates: list[tuple[datetime, datetime, int]] = []

        # Look for the next boundary in this year or next year
        for y in (year, year + 1):
            try:
                start_y = f.dst_start.to_datetime(y)
                end_y_dst = f.dst_end.to_datetime(y)
            except ValueError:
                # Out-of-range year for datetime, just skip
                continue

            if start_y > local_std:
                candidates.append((start_y, start_y, std))

            end_y_std = end_y_dst - dst_delta_td
            if end_y_std > local_std:
                candidates.append((end_y_std, end_y_dst, dst_offset))

        if not candidates:
            return None

        _, local_wall, boundary_offset = min(candidates, key=lambda x: x[0])
        boundary_delta = timedelta(seconds=boundary_offset)
        next_utc = (local_wall - boundary_delta).replace(tzinfo=timezone.utc)
        return next_utc

    @staticmethod
    def _next_meaningful_body_transition(
        body: TimeZoneInfoBody,
        start_index: int,
        current_offset: int,
        current_dst_diff: int,
        current_abbr: str | None,
    ) -> datetime | None:
        """
        Find the next transition that changes the effective ttinfo as defined by
        zoneinfo (_ttinfo equality is utcoff/dstoff/tzname).
        Some TZif files carry duplicate ttinfos; those are skipped.
        """
        for i in range(start_index, len(body.transitions)):
            tr = body.transitions[i]
            if (
                tr.utc_offset_secs != current_offset
                or tr.dst_difference_secs != current_dst_diff
                or tr.abbreviation != current_abbr
            ):
                return tr.transition_time_utc
        return None

    def resolve(self, dt: datetime) -> TimeZoneResolution:
        """
        Resolve this timezone at a given instant.
        Accepts naive (interpreted as UTC) or aware (converted to UTC).
        Returns a TimeZoneResolution with tz-aware UTC `resolution_time`,
        naive local wall `local_time`, and `next_transition` as the UTC datetime
        of the next transition if one is known.
        """
        if dt.tzinfo is None:
            dt_utc = dt.replace(tzinfo=timezone.utc)
        else:
            dt_utc = dt.astimezone(timezone.utc)

        # Normalize to whole seconds for cache key; keep the original timestamp in outputs.
        dt_utc_key = dt_utc.replace(microsecond=0, fold=dt_utc.fold)

        # Check cache
        if self._last_resolution is not None:
            cached_dt_utc: datetime = self._last_resolution.cache_key
            cached_res: TimeZoneResolution = self._last_resolution.resolution

            # Exact match: fast path
            if cached_dt_utc == dt_utc_key:
                off = cached_res.utc_offset_secs
                local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
                return replace(
                    cached_res,
                    resolution_time=dt_utc,
                    local_time=local,
                )

            next_transition = cached_res.next_transition

            # Use range caching when we actually know the next transition
            # and the requested time is between the cached resolution_time
            # and the next_transition.
            if (
                next_transition is not None
                and cached_dt_utc <= dt_utc_key < next_transition
            ):
                off = cached_res.utc_offset_secs
                local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)

                # Build a new resolution for this dt_utc, but reuse the same offset,
                # DST flag, abbr, delta, and next_transition.
                return replace(
                    cached_res,
                    resolution_time=dt_utc,
                    local_time=local,
                )

        body = self.body

        # Case 0: No transitions at all => single ttinfo applies
        if not body.transitions:
            posix_state = self._posix_footer_state(dt_utc)
            off, delta, abbr, in_dst = posix_state or self._initial_tt_state(body)

            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
            next_transition = self._next_posix_transition_utc(dt_utc)

            return self._cache_last_resolution(
                dt_utc_key,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    off,
                    in_dst,
                    abbr,
                    delta,
                    next_transition=next_transition,
                ),
            )

        first = body.transitions[0]
        last = body.transitions[-1]

        # Case 1: Before first transition
        if dt_utc < first.transition_time_utc:
            off, delta, abbr, in_dst = self._initial_tt_state(body)
            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)

            next_transition = self._next_meaningful_body_transition(
                body, 0, off, delta, abbr
            )

            return self._cache_last_resolution(
                dt_utc_key,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    off,
                    in_dst,
                    abbr,
                    delta,
                    next_transition=next_transition,
                ),
            )

        # Case 2: Between transitions (inclusive of the last transition instant)
        if dt_utc <= last.transition_time_utc:
            tr_index = body.find_transition_index(dt_utc)
            if tr_index is None:
                raise ValueError("No valid transition found for the given datetime")
            tr = body.transitions[tr_index]
            off = tr.utc_offset_secs
            delta = tr.dst_difference_secs if tr.is_dst else 0
            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)

            # Next body transition, if there is one.
            next_transition = self._next_meaningful_body_transition(
                body, tr_index + 1, off, delta, tr.abbreviation
            )

            if next_transition is None and self._posix_tz_info is not None:
                # Fall back to POSIX rules after the body ends.
                next_transition = self._next_posix_transition_utc(dt_utc)

            return self._cache_last_resolution(
                dt_utc_key,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    off,
                    tr.is_dst,
                    tr.abbreviation,
                    delta,
                    next_transition=next_transition,
                ),
            )

        # Case 3: After the last transition, use POSIX footer if present
        posix_state = self._posix_footer_state(dt_utc)
        if posix_state is not None:
            off, delta, abbr, in_dst = posix_state
            local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)

            # Now that we're past the end of the TZif body, use the POSIX rules
            # to find the next transition.
            next_transition = self._next_posix_transition_utc(dt_utc)

            return self._cache_last_resolution(
                dt_utc_key,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    off,
                    in_dst,
                    abbr,
                    delta,
                    next_transition=next_transition,
                ),
            )

        # Case 4: No footer; stick to the last known offset, no further transitions known
        off = last.utc_offset_secs
        delta = last.dst_difference_secs if last.is_dst else 0
        local = (dt_utc + timedelta(seconds=off)).replace(tzinfo=None)
        next_transition = None
        return self._cache_last_resolution(
            dt_utc_key,
            TimeZoneResolution(
                self.timezone_name,
                dt_utc,
                local,
                off,
                last.is_dst,
                last.abbreviation,
                delta,
                next_transition=next_transition,
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

    def next_transition(self, dt: datetime) -> datetime | None:
        return self.resolve(dt).next_transition

    @classmethod
    def _read_from_fileobj(
        cls, file: IO[bytes], timezone_name: str, filepath: str
    ) -> "TimeZoneInfo":
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
    def read(cls, timezone_name: str):
        if os.path.isabs(timezone_name):
            raise ValueError(
                "Absolute paths are not allowed in TimeZoneInfo.read(); use from_path() instead."
            )

        normalized_name = cls._validate_timezone_key(timezone_name)

        search_paths: list[str] = []
        tzdir_override = os.environ.get("TZDIR")
        if tzdir_override:
            search_paths.append(os.path.realpath(tzdir_override))
        search_paths.extend(cls._compute_default_tzpath())

        for tz_root in search_paths:
            candidate = os.path.join(tz_root, normalized_name)
            if os.path.isfile(candidate):
                real = os.path.realpath(candidate)
                with open(real, "rb") as file:
                    return cls._read_from_fileobj(file, timezone_name, real)

        # Fallback to tzdata package if present
        file = cls._load_tzdata_from_package(normalized_name)
        with file as f:
            return cls._read_from_fileobj(f, timezone_name, f"tzdata:{normalized_name}")

    @classmethod
    def from_path(cls, path: str, timezone_name: str | None = None) -> "TimeZoneInfo":
        """Read a TZif file directly from an absolute filesystem path."""
        real = os.path.realpath(path)
        with open(real, "rb") as file:
            return cls._read_from_fileobj(file, timezone_name or real, real)

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

    @staticmethod
    def _compute_default_tzpath() -> tuple[str, ...]:
        env_var = os.environ.get("PYTHONTZPATH") or sysconfig.get_config_var("TZPATH")
        if env_var:
            return tuple(path for path in env_var.split(os.pathsep) if path)

        # Fallback paths align with CPython's defaults
        return (
            "/usr/share/zoneinfo",
            "/usr/share/lib/zoneinfo",
            "/etc/zoneinfo",
        )

    @staticmethod
    def _validate_timezone_key(key: str) -> str:
        if os.path.isabs(key):
            raise ValueError("Absolute paths are not allowed as timezone keys")

        # Normalize and ensure the normalized form does not change length (prevents ../)
        normalized = os.path.normpath(key)
        if len(normalized) != len(key) or normalized in (os.curdir, os.pardir, ""):
            raise ValueError(f"Invalid timezone name: {key!r}")

        # Ensure the path stays within a sentinel base
        _base = os.path.normpath(os.path.join("_", "_"))[:-1]
        resolved = os.path.normpath(os.path.join(_base, normalized))
        if not resolved.startswith(_base):
            raise ValueError(f"Invalid timezone name: {key!r}")

        return normalized

    @staticmethod
    def _load_tzdata_from_package(key: str) -> IO[bytes]:
        components = key.split("/")
        package_name = ".".join(["tzdata.zoneinfo"] + components[:-1])
        resource_name = components[-1]
        try:
            return resources.files(package_name).joinpath(resource_name).open("rb")
        except (ImportError, FileNotFoundError, UnicodeEncodeError) as exc:
            raise FileNotFoundError(f"No time zone found with key {key!r}") from exc
