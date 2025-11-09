import os
from datetime import datetime, timedelta, timezone
from zoneinfo import available_timezones

import pytest

from my_zoneinfo.zoneinfo import ZoneInfo
from tzif_parser import TimeZoneInfo


@pytest.mark.parametrize(
    "utc_time, expected_offset",
    [
        (datetime(1800, 1, 1, 0, 0, 0), -17762),
        (datetime(2025, 1, 5, 0, 0, 0), -18000),
        (datetime(2025, 6, 2, 0, 0, 0), -14400),
        (datetime(2039, 1, 5, 0, 0, 0), -18000),
        (datetime(2039, 6, 2, 0, 0, 0), -14400),
    ],
)
def test_utc_to_local(utc_time, expected_offset):
    tz_info = TimeZoneInfo.read("America/New_York")
    local_time = tz_info.utc_to_local(utc_time)
    assert utc_time + timedelta(seconds=expected_offset) == local_time


def test_read_invalid_timezone():
    with pytest.raises(FileNotFoundError):
        TimeZoneInfo.read("Invalid/Timezone")


def test_read_transitions():
    timezones = available_timezones()

    for timezone in timezones:
        tz_info = TimeZoneInfo.read(timezone)
        zoneinfo = ZoneInfo(timezone)

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
            [
                datetime.fromtimestamp(transition)
                for transition in zoneinfo._trans_local[0]
            ],
            [
                datetime.fromtimestamp(transition)
                for transition in zoneinfo._trans_local[1]
            ],
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


def test_find_transition_edges_new_york():
    tz = "America/New_York"
    tz_info = TimeZoneInfo.read(tz)

    # pick a middle transition to have both neighbors
    assert len(tz_info.body.transitions) >= 3
    mid_idx = len(tz_info.body.transitions) // 2
    tr = tz_info.body.transitions[mid_idx]
    t = tr.transition_time_utc  # aware UTC

    # exactly at transition -> should return this transition
    assert tz_info.body.find_transition(t) is tr

    # just before -> previous transition
    prev = tz_info.body.transitions[mid_idx - 1]
    assert tz_info.body.find_transition(t - timedelta(seconds=1)) is prev

    # just after -> still this transition
    assert tz_info.body.find_transition(t + timedelta(seconds=1)) is tr


def test_find_transition_normalizes_naive_to_utc():
    tz = "America/Chicago"
    tz_info = TimeZoneInfo.read(tz)
    # take any transition time (aware UTC)
    tr = tz_info.body.transitions[0]
    aware = tr.transition_time_utc
    naive = aware.replace(tzinfo=None)

    # Both should point to the same transition
    assert tz_info.body.find_transition(aware) is tz_info.body.find_transition(naive)


@pytest.mark.parametrize(
    "tz, samples",
    [
        # US with DST
        (
            "America/New_York",
            [
                datetime(2024, 1, 15, 12, 0, 0),
                datetime(2024, 6, 15, 12, 0, 0),
                datetime(2025, 3, 9, 6, 59, 59),  # just before US DST start 2025
                datetime(2025, 3, 9, 7, 0, 1),  # just after
            ],
        ),
        # Southern hemisphere DST over new year
        (
            "Australia/Sydney",
            [
                datetime(2025, 1, 5, 0, 0, 0),
                datetime(2025, 6, 2, 0, 0, 0),
                datetime(2025, 10, 5, 15, 59, 59),  # near Oct change
                datetime(2025, 10, 5, 16, 0, 1),
            ],
        ),
        # Fixed offset, no DST
        (
            "Africa/Abidjan",  # UTC
            [
                datetime(1990, 1, 1, 0, 0, 0),
                datetime(2025, 1, 1, 0, 0, 0),
                datetime(2050, 7, 1, 12, 0, 0),
            ],
        ),
        # Non-integer hour offset
        (
            "Asia/Kolkata",  # +05:30, no DST
            [
                datetime(2025, 1, 1, 0, 0, 0),
                datetime(2025, 6, 1, 0, 0, 0),
            ],
        ),
    ],
)
def test_utc_to_local_matches_zoneinfo_samples(tz, samples):
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    for utc_dt in samples:
        expected = (
            utc_dt.replace(tzinfo=timezone.utc).astimezone(z).replace(tzinfo=None)
        )
        got = tz_info.utc_to_local(utc_dt)  # accepts naive UTC
        assert got == expected, f"{tz=} {utc_dt=} {got=} {expected=}"


@pytest.mark.parametrize(
    "tz, far_dates",
    [
        ("America/New_York", [datetime(2050, 6, 1), datetime(2099, 12, 1)]),
        ("Australia/Sydney", [datetime(2050, 1, 10), datetime(2099, 7, 10)]),
    ],
)
def test_footer_far_future_matches_zoneinfo(tz, far_dates):
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    # Sanity: we really are after the last on-disk transition
    last_tr = tz_info.body.transitions[-1].transition_time_utc

    for utc_dt in far_dates:
        assert utc_dt.replace(tzinfo=timezone.utc) > last_tr
        expected = (
            utc_dt.replace(tzinfo=timezone.utc).astimezone(z).replace(tzinfo=None)
        )
        got = tz_info.utc_to_local(utc_dt)
        assert got == expected, f"POSIX footer mismatch for {tz} at {utc_dt}"


@pytest.mark.parametrize(
    "tz, utc_dt",
    [
        ("America/Los_Angeles", datetime(2025, 3, 10, 0, 0, 0)),
        ("Europe/London", datetime(1900, 6, 1, 12, 0, 0)),
        ("Asia/Tokyo", datetime(2055, 3, 15, 6, 0, 0)),
    ],
)
def test_naive_and_aware_inputs_equivalent(tz, utc_dt):
    tz_info = TimeZoneInfo.read(tz)
    naive = utc_dt
    aware = utc_dt.replace(tzinfo=timezone.utc)
    assert tz_info.utc_to_local(naive) == tz_info.utc_to_local(aware)


def test_transition_abbreviation_matches_zoneinfo():
    tz = "America/Denver"
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    # Check first 10 transitions (or fewer)
    for tr in tz_info.body.transitions[:10]:
        # one second after transition (to avoid the exact instant ambiguity)
        t1 = (tr.transition_time_utc + timedelta(seconds=1)).astimezone(z)
        # expected abbreviation from zoneinfo at local wall time
        expected_abbrev = t1.tzname()
        # our abbreviation (of the new ttinfo) should match
        assert tr.abbreviation == expected_abbrev


def test_dst_difference_secs_consistent():
    tz = "America/Chicago"
    tz_info = TimeZoneInfo.read(tz)

    for i, tr in enumerate(tz_info.body.transitions):
        if not tr.is_dst:
            continue

        this_off = tr.utc_offset_secs
        # previous non-DST or DST
        prev_off = tz_info.body.transitions[i - 1].utc_offset_secs if i > 0 else None
        # next non-DST or DST
        next_off = (
            tz_info.body.transitions[i + 1].utc_offset_secs
            if i + 1 < len(tz_info.body.transitions)
            else None
        )

        # your implementation prefers adjacent DST offset differences, or falls back to 3600
        possible = set()
        if prev_off is not None:
            possible.add(abs(this_off - prev_off))
        if next_off is not None:
            possible.add(abs(next_off - this_off))
        possible.add(3600)

        assert tr.dst_difference_secs in possible
