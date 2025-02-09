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
        self._wall_standard_flag = WallStandardFlag(
            wall_standard_flags[time_type_indices[transition_index]]
        )
        self._is_utc = bool(is_utc_flags[time_type_indices[transition_index]])
        self._abbreviation = timezone_abbrevs[
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
    def abbreviation(self) -> str:
        return self._abbreviation

    @property
    def utc_offset_secs(self) -> int:
        return self._time_type_info.utc_offset_secs

    @property
    def utc_offset_hours(self) -> float:
        return self.utc_offset_secs / 3600

    @property
    def is_dst(self) -> bool:
        return self._time_type_info.is_dst

    @property
    def wall_standard_flag(self) -> WallStandardFlag:
        return self._wall_standard_flag

    @property
    def is_utc(self) -> bool:
        return self._is_utc
