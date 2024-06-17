from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class WallStandardFlag(Enum):
    """
    Represents the wall/std flag in a TZif file.
    """

    WALL = 0
    STANDARD = 1


@dataclass
class TimeTypeInfo:
    """
    Represents a ttinfo structure in a TZif file.
    """

    utc_offset_secs: int
    is_dst: bool
    _abbrev_index: int
    abbrev: str | None = None
    is_utc = False
    is_wall_standard = WallStandardFlag.WALL

    def set_abbrev(self, timezone_abbrevs: str) -> None:
        self.abbrev, _, _ = timezone_abbrevs[self._abbrev_index :].partition("\x00")


@dataclass
class DstTransition:
    """
    Represents a transition time in a TZif file.
    """

    _transition_time: datetime
    _time_type_info: TimeTypeInfo
    _prev_time_type_info: TimeTypeInfo | None = None

    # TODO: check this logic
    @property
    def transition_time(self) -> datetime:
        match self.is_utc, self.is_wall_standard:
            case False, WallStandardFlag.WALL:
                transition_time = self._transition_time.replace(
                    tzinfo=timezone.utc
                ).astimezone(timezone(self.utc_offset))
                if self._prev_time_type_info:
                    transition_time = transition_time + timedelta(
                        seconds=self._prev_time_type_info.utc_offset_secs
                        - self._time_type_info.utc_offset_secs
                    )
                return transition_time
            case False, WallStandardFlag.STANDARD:
                return self._transition_time.replace(tzinfo=timezone.utc).astimezone(
                    timezone(self.utc_offset)
                )
            case True, WallStandardFlag.WALL:
                # TODO: not sure this one is valid
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


@dataclass
class LeapSecondTransition:
    """
    Represents a leap second entry in a TZif file.
    """

    transition_time: int
    correction: int
