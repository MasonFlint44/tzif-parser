from datetime import datetime
from zoneinfo import ZoneInfo

from .tzif import TimeZoneInfo

TIMEZONE_NAME = "America/Chicago"

tz_info = TimeZoneInfo.read(TIMEZONE_NAME)
next_dst_transition = next(
    (
        transition
        for transition in tz_info.dst_transitions
        if transition.transition_time > datetime.now(ZoneInfo(TIMEZONE_NAME))
    ),
    None,
)
if next_dst_transition is not None:
    local_time = next_dst_transition.transition_time
    utc_time = next_dst_transition.transition_time_utc

pass
