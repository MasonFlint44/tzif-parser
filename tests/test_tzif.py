import os

import pytest

from tzif_parser import TimeZoneInfo


@pytest.mark.parametrize(
    "timezone_name, dst_transition_count, local_time_type_count, abbrevs_count, leap_seconds_count",
    [
        ("America/New_York", 236, 6, 5, 0),
        ("America/Chicago", 236, 8, 6, 0),
        ("America/Denver", 158, 6, 5, 0),
        ("America/Los_Angeles", 186, 6, 5, 0),
    ],
)
def test_read(
    timezone_name,
    dst_transition_count,
    local_time_type_count,
    abbrevs_count,
    leap_seconds_count,
):
    tz_info = TimeZoneInfo.read(timezone_name)

    assert tz_info.timezone_name == timezone_name
    assert tz_info.filepath == os.path.join(
        "/usr/share/zoneinfo", *timezone_name.split("/")
    )
    assert tz_info.version == 2

    assert tz_info.header.dst_transitions_count == dst_transition_count
    assert len(tz_info.body.dst_transitions) == dst_transition_count
    assert len(tz_info.body.time_type_indices) == dst_transition_count

    assert tz_info.header.local_time_type_count == local_time_type_count
    assert tz_info.header.wall_standard_flag_count == local_time_type_count
    assert tz_info.header.is_utc_flag_count == local_time_type_count
    assert len(tz_info.body.time_type_info) == local_time_type_count
    assert len(tz_info.body.wall_standard_flags) == local_time_type_count
    assert len(tz_info.body.is_utc_flags) == local_time_type_count

    assert len(tz_info.body.timezone_abbrevs) == abbrevs_count

    assert len(tz_info.body.leap_second_transitions) == leap_seconds_count
