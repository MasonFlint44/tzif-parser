from datetime import datetime, timedelta, timezone

from .models import TimeTypeInfo, WallStandardFlag


class TimeZoneTransition:
    def __init__(
        self,
        transition_time: datetime,
        time_type_infos: list[TimeTypeInfo],
        time_type_indices: list[int],
        transition_index: int,
        wall_standard_flags: list[WallStandardFlag],
        is_utc_flags: list[int],
        timezone_abbrevs: str,
    ) -> None:
        self._transition_time = transition_time
        self._time_type_infos = time_type_infos
        self._time_type_indices = time_type_indices
        self._transition_index = transition_index
        self._time_type_info = time_type_infos[time_type_indices[transition_index]]
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
            self._time_type_info.abbrev_index :
        ].partition("\x00")[0]

    @property
    def transition_time_local_standard(self) -> datetime:
        if self._transition_index == 0:
            ttinfo = self._time_type_infos[0]
            return self.transition_time_utc.astimezone(
                timezone(timedelta(seconds=ttinfo.utc_offset_secs))
            )
        ttinfo = self._time_type_infos[
            self._time_type_indices[self._transition_index - 1]
        ]
        return self.transition_time_utc.astimezone(
            timezone(timedelta(seconds=ttinfo.utc_offset_secs))
        )

    @property
    def transition_time_local_wall(self) -> datetime:
        return self.transition_time_utc.astimezone(
            timezone(timedelta(seconds=self.utc_offset_secs))
        )

    @property
    def transition_time_utc(self) -> datetime:
        return self._transition_time.replace(tzinfo=timezone.utc)

    @property
    def dst_offset_secs(self) -> int:
        if not self.is_dst:
            return 0
        # Get the ttinfo for the previous transition
        ttinfo = self._time_type_infos[
            self._time_type_indices[self._transition_index - 1]
        ]
        if ttinfo.is_dst:
            return self.utc_offset_secs - ttinfo.utc_offset_secs
        # Get the ttinfo for the next transition
        ttinfo = self._time_type_infos[
            self._time_type_indices[self._transition_index + 1]
        ]
        if ttinfo.is_dst:
            return ttinfo.utc_offset_secs - self.utc_offset_secs
        # If the previous and next ttinfos are not DST, then we return a best guess
        return 3600

    @property
    def dst_offset_hours(self) -> float:
        return self.dst_offset_secs / 3600

    @property
    def utc_offset_secs(self) -> int:
        return self._time_type_info.utc_offset_secs

    @property
    def utc_offset_hours(self) -> float:
        return self.utc_offset_secs / 3600

    @property
    def is_dst(self) -> bool:
        return self._time_type_info.is_dst
