from dataclasses import dataclass
from datetime import time


@dataclass
class TimeZoneInfoBody:
    transition_times: tuple[int, ...]
    time_type_indices: list[int]
    ttinfo_structures: list[tuple[int, bool, int]]
    tz_designations: list[str]
    leap_seconds: list[tuple[int, ...]]
    std_wall_indicators: list[int]
    ut_local_indicators: list[int]


@dataclass
class TimeZoneInfoHeader:
    version: int
    tzh_ttisutcnt: int
    tzh_ttisstdcnt: int
    tzh_leapcnt: int
    tzh_timecnt: int
    tzh_typecnt: int
    tzh_charcnt: int


@dataclass
class PosixTzDateTime:
    month: int
    week: int
    weekday: int
    time: time
