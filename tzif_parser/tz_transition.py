from datetime import datetime, timedelta, timezone

from .models import TimeTypeInfo, WallStandardFlag


class TimeZoneTransition:
    def __init__(
        self,
        transition_time: datetime,
        time_type_infos: list[TimeTypeInfo],
        time_type_indices: list[int],
        transition_index: int,
        wall_standard_flags: list[int],
        is_utc_flags: list[int],
        timezone_abbrevs: str,
    ) -> None:
        self._transition_time = transition_time
        self._time_type_infos = time_type_infos
        self._time_type_indices = time_type_indices
        self._transition_index = transition_index
        self.time_type_info = time_type_infos[time_type_indices[transition_index]]
        self.wall_standard_flag = (
            WallStandardFlag(wall_standard_flags[time_type_indices[transition_index]])
            if len(wall_standard_flags) > 0
            else None
        )
        self.is_utc = (
            bool(is_utc_flags[time_type_indices[transition_index]])
            if len(is_utc_flags) > 0
            else None
        )
        self.abbreviation = timezone_abbrevs[
            self.time_type_info.abbrev_index :
        ].partition("\x00")[0]

    @property
    def transition_time_local_standard(self) -> datetime:
        if self._transition_index == 0:
            # Prefer a non-DST ttinfo if present, else fall back to index 0
            first_std = next(
                (tti for tti in self._time_type_infos if not tti.is_dst),
                self._time_type_infos[0],
            )
            return self.transition_time_utc.astimezone(
                timezone(timedelta(seconds=first_std.utc_offset_secs))
            ).replace(tzinfo=None)
        ttinfo = self._time_type_infos[
            self._time_type_indices[self._transition_index - 1]
        ]
        return self.transition_time_utc.astimezone(
            timezone(timedelta(seconds=ttinfo.utc_offset_secs))
        ).replace(tzinfo=None)

    @property
    def transition_time_local_wall(self) -> datetime:
        return self.transition_time_utc.astimezone(
            timezone(timedelta(seconds=self.utc_offset_secs))
        ).replace(tzinfo=None)

    @property
    def transition_time_utc(self) -> datetime:
        return self._transition_time

    @property
    def dst_difference_secs(self) -> int:
        if not self.is_dst:
            return 0

        # previous
        if self._transition_index > 0:
            prev_tt = self._time_type_infos[
                self._time_type_indices[self._transition_index - 1]
            ]
            if prev_tt.is_dst:
                return self.utc_offset_secs - prev_tt.utc_offset_secs

        # next
        if self._transition_index + 1 < len(self._time_type_indices):
            next_tt = self._time_type_infos[
                self._time_type_indices[self._transition_index + 1]
            ]
            if next_tt.is_dst:
                return next_tt.utc_offset_secs - self.utc_offset_secs

        # fallback if neighbors aren't DST or next doesn't exist
        return 3600

    @property
    def dst_difference_hours(self) -> float:
        return self.dst_difference_secs / 3600

    @property
    def utc_offset_secs(self) -> int:
        return self.time_type_info.utc_offset_secs

    @property
    def utc_offset_hours(self) -> float:
        return self.utc_offset_secs / 3600

    @property
    def is_dst(self) -> bool:
        return self.time_type_info.is_dst
