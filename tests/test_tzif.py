import os
from datetime import datetime

import pytest

from my_zoneinfo._tzpath import available_timezones
from my_zoneinfo.zoneinfo import ZoneInfo
from tzif_parser import TimeZoneInfo


def test_read_invalid_timezone():
    with pytest.raises(FileNotFoundError):
        TimeZoneInfo.read("Invalid/Timezone")


@pytest.mark.parametrize(
    "timezone_name",
    [
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
    ],
)
def test_read_transitions(timezone_name):
    tz_info = TimeZoneInfo.read(timezone_name)
    zoneinfo = ZoneInfo(timezone_name)

    # Build a list of UTC transitions from tz_info
    # Remove the timezone info from the transition times to compare with zoneinfo
    tz_info_utc_transitions = [
        transitition.transition_time_utc.replace(tzinfo=None)
        for transitition in tz_info.body.transitions
    ]
    # Build a list of UTC transitions from zoneinfo
    # Convert the timestamps to datetime objects
    zoneinfo_utc_transitions = [
        datetime.fromtimestamp(transition) for transition in zoneinfo._trans_utc
    ]
    # Compare the UTC transitions from tz_info and zoneinfo
    assert tz_info_utc_transitions == zoneinfo_utc_transitions

    # Build a list of local transitions from tz_info
    # Remove the timezone info from the transition times to compare with zoneinfo
    tz_info_local_wall_transitions = [
        transitition.transition_time_local_wall.replace(tzinfo=None)
        for transitition in tz_info.body.transitions
    ]
    tz_info_local_standard_transitions = [
        transitition.transition_time_local_standard.replace(tzinfo=None)
        for transitition in tz_info.body.transitions
    ]
    # Combine the wall and standard transitions
    tz_info_local_transitions = list(
        zip(tz_info_local_wall_transitions, tz_info_local_standard_transitions)
    )
    # Sort the transitions in reverse order to compare with zoneinfo
    tz_info_local_transitions = [
        sorted([wall, standard], reverse=True)
        for wall, standard in tz_info_local_transitions
    ]
    # Build a list of local transitions from zoneinfo
    # Convert the timestamps to datetime objects
    zoneinfo_local_transitions = [
        [datetime.fromtimestamp(transition) for transition in zoneinfo._trans_local[0]],
        [datetime.fromtimestamp(transition) for transition in zoneinfo._trans_local[1]],
    ]
    # Zip the transitions for comparison with tz_info
    zoneinfo_local_transitions = list(zip(*zoneinfo_local_transitions))

    # Compare the local transitions from tz_info and zoneinfo
    for i, transitions in enumerate(zoneinfo_local_transitions):
        assert tz_info_local_transitions[i] == list(transitions)


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

    assert tz_info.header.transitions_count == dst_transition_count
    assert len(tz_info.body.transition_times) == dst_transition_count
    assert len(tz_info.body.time_type_indices) == dst_transition_count
    assert len(tz_info.body.transitions) == dst_transition_count

    assert tz_info.header.local_time_type_count == local_time_type_count
    assert tz_info.header.wall_standard_flag_count == local_time_type_count
    assert tz_info.header.is_utc_flag_count == local_time_type_count
    assert len(tz_info.body.time_type_infos) == local_time_type_count
    assert len(tz_info.body.wall_standard_flags) == local_time_type_count
    assert len(tz_info.body.is_utc_flags) == local_time_type_count

    assert len(tz_info.body.timezone_abbrevs) == abbrevs_count

    assert len(tz_info.body.leap_second_transitions) == leap_seconds_count


def test_read_all():
    timezones = available_timezones()

    for timezone in timezones:
        tz_info = TimeZoneInfo.read(timezone)

        assert tz_info.timezone_name == timezone
        assert tz_info.filepath == os.path.join(
            "/usr/share/zoneinfo", *timezone.split("/")
        )
        assert tz_info.version >= 2

        assert len(tz_info.body.transition_times) == tz_info.header.transitions_count
        assert len(tz_info.body.time_type_indices) == tz_info.header.transitions_count
        assert len(tz_info.body.transitions) == tz_info.header.transitions_count

        assert len(tz_info.body.time_type_infos) == tz_info.header.local_time_type_count
        assert (
            len(tz_info.body.wall_standard_flags)
            == tz_info.header.wall_standard_flag_count
        )
        assert len(tz_info.body.is_utc_flags) == tz_info.header.is_utc_flag_count

        assert len(tz_info.body.timezone_abbrevs) >= 1

        assert len(tz_info.body.leap_second_transitions) == 0
