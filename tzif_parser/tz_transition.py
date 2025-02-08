from datetime import datetime, timedelta, timezone

from .models import TimeTypeInfo, WallStandardFlag


class TimeZoneTransition:
    def __init__(
        self,
        transition_time: datetime,
        time_type_info: TimeTypeInfo,
        wall_standard_flag: WallStandardFlag,
        is_utc: bool,
        abbreviation: str,
    ) -> None:
        self._transition_time = transition_time
        self._time_type_info = time_type_info
        self._wall_standard_flag = wall_standard_flag
        self._is_utc = is_utc
        self._abbreviation = abbreviation

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

    def __repr__(self) -> str:
        return (
            f"TimeZoneTransition(transition_time={self._transition_time!r}, "
            f"time_type_info={self._time_type_info!r}, "
            f"wall_standard_flag={self._wall_standard_flag!r}, "
            f"is_utc={self._is_utc!r}, "
            f"abbreviation={self._abbreviation!r})"
        )
