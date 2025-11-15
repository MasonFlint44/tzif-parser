import os
from datetime import datetime, timedelta, timezone
from zoneinfo import available_timezones

import pytest
from zoneinfo_shim.zoneinfo import ZoneInfo

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
def test_resolve_local_time_matches_offset_cases(utc_time, expected_offset):
    tz_info = TimeZoneInfo.read("America/New_York")
    res = tz_info.resolve(utc_time)
    assert res.local_time == utc_time + timedelta(seconds=expected_offset)
    assert res.utc_offset_secs == expected_offset


def test_read_invalid_timezone():
    with pytest.raises(FileNotFoundError):
        TimeZoneInfo.read("Invalid/Timezone")


def test_read_transitions():
    timezones = available_timezones()

    for timezone_name in timezones:
        tz_info = TimeZoneInfo.read(timezone_name)
        zoneinfo = ZoneInfo(timezone_name)

        # Build a list of UTC transitions from tz_info
        tz_info_utc_transitions = [
            transitition.transition_time_utc.replace(tzinfo=None)
            for transitition in tz_info.body.transitions
        ]
        # Build a list of UTC transitions from zoneinfo (python impl via zoneinfo_shim)
        zoneinfo_utc_transitions = [
            datetime.fromtimestamp(transition) for transition in zoneinfo._trans_utc
        ]
        assert tz_info_utc_transitions == zoneinfo_utc_transitions

        # Build a list of local transitions from tz_info
        tz_info_local_wall_transitions = [
            transitition.transition_time_local_wall.replace(tzinfo=None)
            for transitition in tz_info.body.transitions
        ]
        tz_info_local_standard_transitions = [
            transitition.transition_time_local_standard.replace(tzinfo=None)
            for transitition in tz_info.body.transitions
        ]
        tz_info_local_transitions = list(
            zip(tz_info_local_wall_transitions, tz_info_local_standard_transitions)
        )
        tz_info_local_transitions = [
            sorted([wall, standard], reverse=True)
            for wall, standard in tz_info_local_transitions
        ]

        # Build a list of local transitions from zoneinfo
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
        zoneinfo_local_transitions = list(zip(*zoneinfo_local_transitions))

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

    for timezone_name in timezones:
        tz_info = TimeZoneInfo.read(timezone_name)

        assert tz_info.timezone_name == timezone_name
        assert tz_info.filepath == os.path.join(
            "/usr/share/zoneinfo", *timezone_name.split("/")
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
    assert tz_info.body.find_transition_index(t) == mid_idx

    # just before -> previous transition
    assert tz_info.body.find_transition_index(t - timedelta(seconds=1)) == mid_idx - 1

    # just after -> still this transition
    assert tz_info.body.find_transition_index(t + timedelta(seconds=1)) == mid_idx


def test_find_transition_normalizes_naive_to_utc():
    tz = "America/Chicago"
    tz_info = TimeZoneInfo.read(tz)
    # take any transition time (aware UTC)
    tr = tz_info.body.transitions[0]
    aware = tr.transition_time_utc
    naive = aware.replace(tzinfo=None)

    # Both should point to the same transition
    assert tz_info.body.find_transition_index(
        aware
    ) == tz_info.body.find_transition_index(naive)


@pytest.mark.parametrize(
    "tz, samples",
    [
        (
            "America/New_York",
            [
                datetime(2024, 1, 15, 12, 0, 0),
                datetime(2024, 6, 15, 12, 0, 0),
                datetime(2025, 3, 9, 6, 59, 59),
                datetime(2025, 3, 9, 7, 0, 1),
            ],
        ),
        (
            "Australia/Sydney",
            [
                datetime(2025, 1, 5, 0, 0, 0),
                datetime(2025, 6, 2, 0, 0, 0),
                datetime(2025, 10, 5, 15, 59, 59),
                datetime(2025, 10, 5, 16, 0, 1),
            ],
        ),
        (
            "Africa/Abidjan",
            [
                datetime(1990, 1, 1, 0, 0, 0),
                datetime(2025, 1, 1, 0, 0, 0),
                datetime(2050, 7, 1, 12, 0, 0),
            ],
        ),
        (
            "Asia/Kolkata",
            [
                datetime(2025, 1, 1, 0, 0, 0),
                datetime(2025, 6, 1, 0, 0, 0),
            ],
        ),
    ],
)
def test_resolve_matches_zoneinfo_samples(tz, samples):
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    for utc_dt in samples:
        expected = (
            utc_dt.replace(tzinfo=timezone.utc).astimezone(z).replace(tzinfo=None)
        )
        got = tz_info.resolve(utc_dt).local_time  # accepts naive UTC
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

    last_tr = tz_info.body.transitions[-1].transition_time_utc

    for utc_dt in far_dates:
        assert utc_dt.replace(tzinfo=timezone.utc) > last_tr
        expected = (
            utc_dt.replace(tzinfo=timezone.utc).astimezone(z).replace(tzinfo=None)
        )
        got = tz_info.resolve(utc_dt).local_time
        assert got == expected, f"POSIX footer mismatch for {tz} at {utc_dt}"


@pytest.mark.parametrize(
    "tz, utc_dt",
    [
        ("America/Los_Angeles", datetime(2025, 3, 10, 0, 0, 0)),
        ("Europe/London", datetime(1900, 6, 1, 12, 0, 0)),
        ("Asia/Tokyo", datetime(2055, 3, 15, 6, 0, 0)),
    ],
)
def test_resolve_naive_and_aware_inputs_equivalent(tz, utc_dt):
    tz_info = TimeZoneInfo.read(tz)
    naive = tz_info.resolve(utc_dt)
    aware = tz_info.resolve(utc_dt.replace(tzinfo=timezone.utc))
    assert naive.local_time == aware.local_time
    assert naive.utc_offset_secs == aware.utc_offset_secs
    assert naive.is_dst == aware.is_dst
    assert naive.abbreviation == aware.abbreviation
    assert naive.dst_difference_secs == aware.dst_difference_secs


def test_transition_abbreviation_matches_zoneinfo():
    tz = "America/Denver"
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    # Check first 10 transitions (or fewer)
    for tr in tz_info.body.transitions[:10]:
        t1 = (tr.transition_time_utc + timedelta(seconds=1)).astimezone(z)
        expected_abbrev = t1.tzname()
        assert tr.abbreviation == expected_abbrev


def test_dst_difference_secs_consistent():
    tz = "America/Chicago"
    tz_info = TimeZoneInfo.read(tz)

    for i, tr in enumerate(tz_info.body.transitions):
        if not tr.is_dst:
            continue

        this_off = tr.utc_offset_secs
        prev_off = tz_info.body.transitions[i - 1].utc_offset_secs if i > 0 else None
        next_off = (
            tz_info.body.transitions[i + 1].utc_offset_secs
            if i + 1 < len(tz_info.body.transitions)
            else None
        )

        possible = set()
        if prev_off is not None:
            possible.add(abs(this_off - prev_off))
        if next_off is not None:
            possible.add(abs(next_off - this_off))
        possible.add(3600)

        assert tr.dst_difference_secs in possible


def test_resolve_field_shapes_and_types():
    tz_info = TimeZoneInfo.read("America/New_York")
    utc_dt = datetime(2025, 3, 1, 12, 0, 0)

    res = tz_info.resolve(utc_dt)

    # resolution_time must be tz-aware UTC
    assert res.resolution_time.tzinfo is timezone.utc
    # local_time must be naive
    assert res.local_time.tzinfo is None
    # timezone_name should echo input name
    assert res.timezone_name == "America/New_York"
    # offset is integer seconds; abbreviation is str|None; is_dst is bool; dst_difference_secs is int
    assert isinstance(res.utc_offset_secs, int)
    assert isinstance(res.is_dst, bool)
    assert (res.abbreviation is None) or isinstance(res.abbreviation, str)
    assert isinstance(res.dst_difference_secs, int)


def test_resolve_abbreviation_matches_zoneinfo_simple_samples():
    tz = "America/Los_Angeles"
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    for utc_dt in [
        datetime(2025, 1, 15, 18, 0, 0),
        datetime(2025, 7, 15, 18, 0, 0),
    ]:
        res = tz_info.resolve(utc_dt)
        zdt = utc_dt.replace(tzinfo=timezone.utc).astimezone(z)
        assert res.abbreviation == zdt.tzname()


def test_resolve_is_dst_matches_zoneinfo():
    tz = "Europe/Berlin"
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    for utc_dt in [
        datetime(2025, 2, 1, 12, 0, 0),
        datetime(2025, 6, 1, 12, 0, 0),
    ]:
        res = tz_info.resolve(utc_dt)
        zdt = utc_dt.replace(tzinfo=timezone.utc).astimezone(z)
        expected_is_dst = bool(zdt.dst())
        assert res.is_dst == expected_is_dst


def test_resolve_exactly_at_transition_uses_new_ttinfo():
    tz = "America/Chicago"
    tz_info = TimeZoneInfo.read(tz)

    # pick a middle transition
    assert len(tz_info.body.transitions) >= 3
    mid_idx = len(tz_info.body.transitions) // 2
    tr = tz_info.body.transitions[mid_idx]

    res = tz_info.resolve(tr.transition_time_utc)  # aware UTC instant
    assert res.utc_offset_secs == tr.utc_offset_secs
    assert res.is_dst == tr.is_dst
    assert res.abbreviation == tr.abbreviation


def test_resolve_before_first_and_after_last_matches_zoneinfo():
    for tz in ["America/New_York", "Australia/Sydney"]:
        tz_info = TimeZoneInfo.read(tz)
        z = ZoneInfo(tz)

        first_utc = tz_info.body.transitions[0].transition_time_utc
        last_utc = tz_info.body.transitions[-1].transition_time_utc

        before = first_utc - timedelta(days=365)
        after = last_utc + timedelta(days=365 * 10)

        for utc_dt in [before, after]:
            expected = utc_dt.astimezone(z).replace(tzinfo=None)
            got = tz_info.resolve(utc_dt).local_time
            assert got == expected, f"{tz} mismatch @ {utc_dt.isoformat()}"


def test_next_transition_before_first_transition():
    tzinfo = TimeZoneInfo.read("America/New_York")
    body = tzinfo.body

    first = body.transitions[0]
    # Pick a UTC time well before the first transition
    dt_utc = first.transition_time_utc - timedelta(days=365)

    res = tzinfo.resolve(dt_utc)

    assert res.next_transition is not None
    assert res.next_transition == first.transition_time_utc
    # Sanity: next_transition is in UTC and in the future relative to dt_utc
    assert res.next_transition.tzinfo is timezone.utc
    assert res.next_transition > dt_utc.replace(tzinfo=timezone.utc)


def test_next_transition_between_transitions():
    tzinfo = TimeZoneInfo.read("America/New_York")
    body = tzinfo.body

    # Choose a transition safely away from the ends so there IS a "next" one
    middle_index = len(body.transitions) // 2 - 1
    assert middle_index >= 0
    assert middle_index + 1 < len(body.transitions)

    current_tr = body.transitions[middle_index]
    next_tr = body.transitions[middle_index + 1]

    # Pick a UTC instant strictly between these two transitions
    mid_delta = (next_tr.transition_time_utc - current_tr.transition_time_utc) / 2
    dt_utc = current_tr.transition_time_utc + mid_delta

    res = tzinfo.resolve(dt_utc)

    # We should still be in the regime of TZif body transitions,
    # so next_transition should be the next body transition.
    assert res.next_transition == next_tr.transition_time_utc


def test_next_transition_after_last_transition_uses_posix_footer():
    tzinfo = TimeZoneInfo.read("America/New_York")

    # If this zone doesn't have a footer, this test is not applicable.
    if tzinfo._posix_tz_info is None:  # type: ignore[attr-defined]
        pytest.skip("Zone has no POSIX footer; cannot test POSIX-based next_transition")

    body = tzinfo.body
    footer = tzinfo.footer

    last = body.transitions[-1]
    # Pick a UTC instant comfortably after the last TZif body transition
    dt_utc = last.transition_time_utc + timedelta(days=365)

    res = tzinfo.resolve(dt_utc)

    # We should now be in the "POSIX footer" regime, so next_transition should
    # come from the footer rules.
    assert res.next_transition is not None

    # Reproduce the POSIX-standard-time logic used in TimeZoneInfo._next_posix_transition_utc
    std = footer.utc_offset_secs
    local_std = (dt_utc + timedelta(seconds=std)).replace(tzinfo=None)
    year = local_std.year

    if footer.dst_start is None or footer.dst_end is None:
        # If this ever happens, next_transition should be None by design.
        assert res.next_transition is None
        return

    candidates = []
    for y in (year, year + 1):
        start_y = footer.dst_start.to_datetime(y)
        end_y = footer.dst_end.to_datetime(y)
        if start_y > local_std:
            candidates.append(start_y)
        if end_y > local_std:
            candidates.append(end_y)

    # There should be at least one upcoming boundary
    assert candidates
    expected_next_local_std = min(candidates)
    expected_next_utc = (expected_next_local_std - timedelta(seconds=std)).replace(
        tzinfo=timezone.utc
    )

    assert res.next_transition == expected_next_utc
    # Sanity: it’s in the future relative to the query instant
    assert res.next_transition > dt_utc.replace(tzinfo=timezone.utc)
