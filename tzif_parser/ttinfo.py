from .models import WallStandardFlag


class TimeTypeInfo:
    """
    Represents a ttinfo structure in a TZif file.
    """

    def __init__(
        self,
        utc_offset_secs: int,
        is_dst: bool,
        abbrev_index: int,
    ) -> None:
        self.utc_offset_secs = utc_offset_secs
        self.is_dst = is_dst
        self._abbrev_index = abbrev_index
        self.timezone_abbrevs: str | None = None
        self.is_utc = False
        self.is_wall_standard = WallStandardFlag.WALL

    @property
    def abbrev(self) -> str:
        if self.timezone_abbrevs is None:
            raise ValueError("Time zone abbreviations not set.")
        else:
            return self.timezone_abbrevs[self._abbrev_index :].partition("\x00")[0]
