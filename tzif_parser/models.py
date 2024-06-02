from dataclasses import dataclass
from datetime import datetime
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

    transition_time: datetime
    time_type_info: TimeTypeInfo | None = None


@dataclass
class LeapSecondTransition:
    """
    Represents a leap second entry in a TZif file.
    """

    transition_time: int
    correction: int
