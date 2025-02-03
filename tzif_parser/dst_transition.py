from datetime import datetime, timedelta, timezone

from .models import WallStandardFlag
from .ttinfo import TimeTypeInfo


class DstTransition:
    """
    Represents a transition time in a TZif file.
    """

    def __init__(
        self,
        transition_time: datetime,
        time_type_info: TimeTypeInfo,
        prev_time_type_info: TimeTypeInfo | None = None,
    ) -> None:
        self._transition_time = transition_time
        self._time_type_info = time_type_info
        self._prev_time_type_info = prev_time_type_info

    @property
    def dst_adjustment(self) -> timedelta:
        if self._prev_time_type_info is None:
            raise ValueError("Previous time type info not set.")
        return timedelta(
            seconds=self._prev_time_type_info.utc_offset_secs
            - self._time_type_info.utc_offset_secs
        )

    @property
    def dst_adjustment_hours(self) -> float:
        return self.dst_adjustment.total_seconds() / 3600

    @property
    def transition_time(self) -> datetime:
        match self.is_utc, self.is_wall_standard:
            case False, WallStandardFlag.WALL:
                transition_time = self._transition_time.replace(
                    tzinfo=timezone.utc
                ).astimezone(timezone(self.utc_offset))
                if self._prev_time_type_info:
                    transition_time = transition_time + self.dst_adjustment
                return transition_time
            case False, WallStandardFlag.STANDARD:
                return self._transition_time.replace(tzinfo=timezone.utc).astimezone(
                    timezone(self.utc_offset)
                )
            case True, WallStandardFlag.WALL:
                raise ValueError("UTC time cannot be wall time.")
            case True, WallStandardFlag.STANDARD:
                return self._transition_time.replace(tzinfo=timezone.utc)
            case _:
                raise ValueError("Invalid state.")

    @property
    def transition_time_local(self) -> datetime:
        return (
            self.transition_time
            if self.transition_time.tzinfo != timezone.utc
            else self.transition_time.astimezone(timezone(self.utc_offset))
        )

    @property
    def transition_time_utc(self) -> datetime:
        return (
            self.transition_time
            if self.transition_time.tzinfo == timezone.utc
            else self.transition_time.astimezone(timezone.utc)
        )

    @property
    def utc_offset(self) -> timedelta:
        return timedelta(seconds=self._ttinfo.utc_offset_secs)

    @property
    def utc_offset_hours(self) -> float:
        return self.utc_offset.total_seconds() / 3600

    @property
    def is_dst(self) -> bool:
        return self._ttinfo.is_dst

    @property
    def abbreviation(self) -> str | None:
        return self._ttinfo.abbrev

    @property
    def is_utc(self) -> bool:
        return self._ttinfo.is_utc

    @property
    def is_wall_standard(self) -> WallStandardFlag:
        return self._ttinfo.is_wall_standard

    @property
    def _ttinfo(self) -> TimeTypeInfo:
        if not self._time_type_info:
            raise ValueError("Time type info not set.")
        return self._time_type_info
