import os
from collections import namedtuple
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .models import TimeZoneResolution
from .posix import PosixTzInfo
from .tzif_body import TimeZoneInfoBody
from .tzif_header import TimeZoneInfoHeader

TimeZoneResolutionCache = namedtuple(
    "TimeZoneResolutionCache", ["resolution_time", "resolution"]
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
        self, dt_utc: datetime, resolution: TimeZoneResolution
    ) -> TimeZoneResolution:
        self._last_resolution = TimeZoneResolutionCache(dt_utc, resolution)
        return resolution

    def _leap_correction_seconds(self, dt_utc: datetime, body: TimeZoneInfoBody) -> int:
        idx = body.find_leap_second_index(dt_utc)
        if idx is None:
            return 0
        return body.leap_second_transitions[idx].correction

    def _next_leap_transition_utc(
        self, dt_utc: datetime, body: TimeZoneInfoBody
    ) -> datetime | None:
        idx = body.find_leap_second_index(dt_utc)
        if idx is None:
            next_idx = 0
        else:
            next_idx = idx + 1

        if next_idx >= len(body.leap_second_transitions):
            return None
        return (
            _EPOCH
            + timedelta(seconds=body.leap_second_transitions[next_idx].transition_time)
        ).replace(tzinfo=timezone.utc)

    def _merge_leap_transition(
        self,
        next_transition: datetime | None,
        dt_utc: datetime,
        body: TimeZoneInfoBody,
    ) -> datetime | None:
        leap_next = self._next_leap_transition_utc(dt_utc, body)
        if leap_next is None:
            return next_transition
        if next_transition is None or leap_next < next_transition:
            return leap_next
        return next_transition

    def _posix_footer_state(
        self, dt_utc: datetime
    ) -> tuple[int, int, str | None, bool] | None:
        f = self.footer
        if f is None:
            return None

        std = f.utc_offset_secs
        dst_offset = f.dst_offset_secs if f.dst_offset_secs is not None else std + 3600
        dst_delta = dst_offset - std

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

        std = f.utc_offset_secs
        dst_offset = f.dst_offset_secs if f.dst_offset_secs is not None else std + 3600
        dst_delta = timedelta(seconds=dst_offset - std)

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

            end_y_std = end_y_dst - dst_delta
            if end_y_std > local_std:
                candidates.append((end_y_std, end_y_dst, dst_offset))

        if not candidates:
            return None

        _, local_wall, boundary_offset = min(candidates, key=lambda x: x[0])
        boundary_delta = timedelta(seconds=boundary_offset)
        next_utc = (local_wall - boundary_delta).replace(tzinfo=timezone.utc)
        return next_utc

    def resolve(self, dt: datetime) -> TimeZoneResolution:
        """
        Resolve this timezone at a given instant.
        Accepts naive (interpreted as UTC) or aware (converted to UTC).
        Returns a TimeZoneResolution with tz-aware UTC `resolution_time`,
        naive local wall `local_time`, and `next_transition` as the UTC datetime
        of the next transition if one is known.
        """
        # Normalize to whole seconds to improve cache hits (preserve fold info)
        if dt.tzinfo is None:
            dt_utc = dt.replace(tzinfo=timezone.utc, microsecond=0)
        else:
            dt_no_subsec = dt.replace(microsecond=0, fold=dt.fold)
            dt_utc = dt_no_subsec.astimezone(timezone.utc)

        # Check cache
        if self._last_resolution is not None:
            cached_dt_utc: datetime = self._last_resolution.resolution_time
            cached_res: TimeZoneResolution = self._last_resolution.resolution

            # Exact match: fast path
            if cached_dt_utc == dt_utc:
                return cached_res

            next_transition = cached_res.next_transition

            # Use range caching when we actually know the next transition
            # and the requested time is between the cached resolution_time
            # and the next_transition.
            if (
                next_transition is not None
                and cached_dt_utc <= dt_utc < next_transition
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
        leap_corr = self._leap_correction_seconds(dt_utc, body)

        # Case 0: No transitions at all => single ttinfo applies
        if not body.transitions:
            posix_state = self._posix_footer_state(dt_utc)
            if posix_state is not None:
                off, delta, abbr, in_dst = posix_state
            else:
                std = next((x for x in body.time_type_infos if not x.is_dst), None)
                tt = std if std is not None else body.time_type_infos[0]
                delta = (
                    (tt.utc_offset_secs - std.utc_offset_secs)
                    if (tt.is_dst and std)
                    else 0
                )
                off = tt.utc_offset_secs
                abbr = body.get_abbrev_by_index(tt.abbrev_index)
                in_dst = tt.is_dst

            effective_off = off + leap_corr
            local = (dt_utc + timedelta(seconds=effective_off)).replace(tzinfo=None)
            next_transition = self._merge_leap_transition(
                self._next_posix_transition_utc(dt_utc),
                dt_utc,
                body,
            )

            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    effective_off,
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
            std = next((x for x in body.time_type_infos if not x.is_dst), None)
            tt = std if std is not None else body.time_type_infos[0]
            delta = (
                (tt.utc_offset_secs - std.utc_offset_secs) if (tt.is_dst and std) else 0
            )
            off = tt.utc_offset_secs
            abbr = body.get_abbrev_by_index(tt.abbrev_index)
            effective_off = off + leap_corr
            local = (dt_utc + timedelta(seconds=effective_off)).replace(tzinfo=None)

            next_transition = self._merge_leap_transition(
                first.transition_time_utc, dt_utc, body
            )

            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    effective_off,
                    tt.is_dst,
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
            effective_off = off + leap_corr
            local = (dt_utc + timedelta(seconds=effective_off)).replace(tzinfo=None)

            # Next body transition, if there is one.
            if tr_index + 1 < len(body.transitions):
                next_transition = body.transitions[tr_index + 1].transition_time_utc
            else:
                # We are at the last transition instant in the TZif body.
                # If a POSIX footer exists, use it to compute the next
                # transition boundary; otherwise, we truly don't know of
                # any future transitions.
                if self._posix_tz_info is not None:
                    next_transition = self._next_posix_transition_utc(dt_utc)
                else:
                    next_transition = None

            next_transition = self._merge_leap_transition(next_transition, dt_utc, body)

            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    effective_off,
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
            effective_off = off + leap_corr
            local = (dt_utc + timedelta(seconds=effective_off)).replace(tzinfo=None)

            # Now that we're past the end of the TZif body, use the POSIX rules
            # to find the next transition.
            next_transition = self._merge_leap_transition(
                self._next_posix_transition_utc(dt_utc),
                dt_utc,
                body,
            )

            return self._cache_last_resolution(
                dt_utc,
                TimeZoneResolution(
                    self.timezone_name,
                    dt_utc,
                    local,
                    effective_off,
                    in_dst,
                    abbr,
                    delta,
                    next_transition=next_transition,
                ),
            )

        # Case 4: No footer; stick to the last known offset, no further transitions known
        off = last.utc_offset_secs
        delta = last.dst_difference_secs if last.is_dst else 0
        effective_off = off + leap_corr
        local = (dt_utc + timedelta(seconds=effective_off)).replace(tzinfo=None)
        next_transition = self._merge_leap_transition(None, dt_utc, body)

        return self._cache_last_resolution(
            dt_utc,
            TimeZoneResolution(
                self.timezone_name,
                dt_utc,
                local,
                effective_off,
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
    def read(cls, timezone_name: str):
        timezone_dir = os.environ.get("TZDIR", "/usr/share/zoneinfo")
        timezone_dir = os.path.realpath(timezone_dir)
        normalized_name = os.path.normpath(timezone_name)
        if (
            not normalized_name
            or normalized_name in (os.curdir, os.pardir)
            or normalized_name.startswith("..")
            or os.path.isabs(normalized_name)
        ):
            raise ValueError(f"Invalid timezone name: {timezone_name!r}")

        filepath = os.path.realpath(os.path.join(timezone_dir, normalized_name))
        try:
            common = os.path.commonpath([timezone_dir, filepath])
        except ValueError:
            raise ValueError(f"Invalid timezone name: {timezone_name!r}") from None
        if common != timezone_dir:
            raise ValueError(f"Invalid timezone name: {timezone_name!r}")
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
