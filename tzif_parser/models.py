from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class TimeZoneResolution:
    """
    Resolution of a timezone at a specific instant.
    """

    timezone_name: str
    resolution_time: datetime  # tz-aware UTC
    local_time: datetime  # naive local wall time
    utc_offset_secs: int
    is_dst: bool
    abbreviation: str | None
    dst_difference_secs: int


class WallStandardFlag(Enum):
    """
    Represents the wall/std flag in a TZif file.
    """

    WALL = 0
    STANDARD = 1


@dataclass
class LeapSecondTransition:
    """
    Represents a leap second entry in a TZif file.
    """

    transition_time: int
    correction: int


@dataclass
class TimeTypeInfo:
    """
    Represents a ttinfo structure in a TZif file.
    """

    utc_offset_secs: int
    is_dst: bool
    abbrev_index: int
