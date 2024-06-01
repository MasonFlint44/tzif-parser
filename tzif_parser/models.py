from dataclasses import dataclass


@dataclass
class TTInfo:
    """
    Represents a ttinfo structure in a TZif file.
    """

    utc_offset_secs: int
    is_dst: bool
    abbrev_index: int


@dataclass
class LeapSecond:
    """
    Represents a leap second entry in a TZif file.
    """

    transition_time: int
    correction: int
