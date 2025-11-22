import io
import os
import shutil
import struct
from datetime import datetime, timedelta, timezone
from zoneinfo import available_timezones

import pytest

from tzif_parser import TimeZoneInfo
from tzif_parser.models import LeapSecondTransition, TimeTypeInfo
from tzif_parser.posix import PosixTzDateTime, PosixTzInfo
from tzif_parser.tzif_body import TimeZoneInfoBody
from tzif_parser.tzif_header import TimeZoneInfoHeader
from zoneinfo_shim.zoneinfo import ZoneInfo


def _find_next_zoneinfo_transition(
    zone: ZoneInfo, start: datetime, end: datetime | None = None
) -> datetime | None:
    step = timedelta(hours=6)
    limit = end or (start + timedelta(days=366 * 3))
    prev_offset = start.astimezone(zone).utcoffset()
    probe = start

    while probe < limit:
        next_probe = min(probe + step, limit)
        next_offset = next_probe.astimezone(zone).utcoffset()
        if next_offset != prev_offset:
            low_ts = int(probe.timestamp())
            high_ts = int(next_probe.timestamp())
            while low_ts + 1 < high_ts:
                mid_ts = (low_ts + high_ts) // 2
                mid = datetime.fromtimestamp(mid_ts, tz=timezone.utc)
                if mid.astimezone(zone).utcoffset() == prev_offset:
                    low_ts = mid_ts
                else:
                    high_ts = mid_ts
            return datetime.fromtimestamp(high_ts, tz=timezone.utc)
        probe = next_probe

    return None


def _zoneinfo_transitions_in_year(zone: ZoneInfo, year: int) -> list[datetime]:
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    transitions: list[datetime] = []
    probe = start

    while True:
        next_transition = _find_next_zoneinfo_transition(zone, probe, end)
        if next_transition is None or next_transition >= end:
            break
        transitions.append(next_transition)
        probe = next_transition + timedelta(seconds=1)

    return transitions


def _posix_only_timezone() -> TimeZoneInfo:
    header = TimeZoneInfoHeader(
        version=1,
        is_utc_flag_count=1,
        wall_standard_flag_count=1,
        leap_second_transitions_count=0,
        transitions_count=0,
        local_time_type_count=1,
        timezone_abbrev_byte_count=len("STD\x00DST\x00"),
    )
    body = TimeZoneInfoBody(
        transition_times=[],
        leap_second_transitions=[],
        time_type_infos=[
            TimeTypeInfo(
                utc_offset_secs=-5 * 3600,
                is_dst=False,
                abbrev_index=0,
            )
        ],
        time_type_indices=[],
        timezone_abbrevs="STD\x00DST\x00",
        wall_standard_flags=[0],
        is_utc_flags=[0],
    )
    posix_info = PosixTzInfo(
        posix_string="STD5DST,M3.2.0/2,M11.1.0/2",
        standard_abbrev="STD",
        utc_offset_secs=-5 * 3600,
        dst_abbrev="DST",
        dst_offset_secs=-4 * 3600,
        dst_start=PosixTzDateTime(3, 2, 0, 2, 0, 0),
        dst_end=PosixTzDateTime(11, 1, 0, 2, 0, 0),
    )
    return TimeZoneInfo(
        "Test/PosixOnly",
        "/tmp/Test/PosixOnly",
        header,
        body,
        posix_tz_info=posix_info,
    )


def _leap_expiring_timezone() -> TimeZoneInfo:
    header = TimeZoneInfoHeader(
        version=1,
        is_utc_flag_count=1,
        wall_standard_flag_count=1,
        leap_second_transitions_count=3,
        transitions_count=0,
        local_time_type_count=1,
        timezone_abbrev_byte_count=len("UTC\x00"),
    )
    body = TimeZoneInfoBody(
        transition_times=[],
        leap_second_transitions=[
            LeapSecondTransition(transition_time=10, correction=1),
            LeapSecondTransition(transition_time=20, correction=2),
            LeapSecondTransition(transition_time=20, correction=2, is_expiration=True),
        ],
        time_type_infos=[
            TimeTypeInfo(
                utc_offset_secs=0,
                is_dst=False,
                abbrev_index=0,
            )
        ],
        time_type_indices=[],
        timezone_abbrevs="UTC\x00",
        wall_standard_flags=[0],
        is_utc_flags=[0],
        leap_second_expiration=datetime(1970, 1, 1, tzinfo=timezone.utc)
        + timedelta(seconds=20),
    )
    return TimeZoneInfo(
        "Test/LeapExpiration",
        "/tmp/Test/LeapExpiration",
        header,
        body,
    )


def test_read_transition_times_handles_negative(monkeypatch):
    from tzif_parser import tzif_body

    class DummyDateTime:
        @staticmethod
        def fromtimestamp(*args, **kwargs):
            raise OSError("boom")

    monkeypatch.setattr(tzif_body, "datetime", DummyDateTime)

    data = struct.pack(">2i", -1, 1)
    buffer = io.BytesIO(data)
    times = tzif_body.TimeZoneInfoBody._read_transition_times(buffer, 2, 1)
    assert times[0] == datetime(1969, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert times[1] == datetime(1970, 1, 1, 0, 0, 1, tzinfo=timezone.utc)


def test_read_transition_times_clamps_out_of_range():
    # Far-future/past timestamps that overflow datetime should not abort parsing.
    data = struct.pack(">2q", 10**12, -10**12)  # way beyond datetime limits
    buffer = io.BytesIO(data)
    times = TimeZoneInfoBody._read_transition_times(buffer, 2, 2)

    assert times[0] == datetime.max.replace(tzinfo=timezone.utc)
    assert times[1] == datetime.min.replace(tzinfo=timezone.utc)


def test_posix_transition_time_supports_extended_hours():
    late = PosixTzDateTime(3, 2, 0, 26, 0, 0).to_datetime(2024)
    early = PosixTzDateTime(3, 2, 0, -2, 30, 0).to_datetime(2024)

    assert late == datetime(2024, 3, 11, 2, 0, 0)
    assert early == datetime(2024, 3, 9, 22, 30, 0)


def test_posix_parser_allows_comma_in_abbreviation():
    buffer = io.BytesIO(b"\n<UTC+05,30>-5:30\n")
    info = PosixTzInfo.read(buffer)

    assert info is not None
    assert info.standard_abbrev == "UTC+05,30"
    assert info.utc_offset_secs == 5 * 3600 + 30 * 60


def test_read_leap_seconds_marks_expiration_entry():
    data = struct.pack(
        ">qi",
        100,
        1,
    ) + struct.pack(
        ">qi",
        100,
        1,
    )
    buffer = io.BytesIO(data)
    leaps, expiration = TimeZoneInfoBody._read_leap_seconds(buffer, 2, 4)

    assert len(leaps) == 2
    assert leaps[0].is_expiration is False
    assert leaps[1].is_expiration is True
    assert expiration == datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=100
    )


def test_read_leap_seconds_clamps_out_of_range():
    big = 10**12  # far beyond datetime range
    data = struct.pack(">qi", big, 1) + struct.pack(">qi", big, 1)
    buffer = io.BytesIO(data)
    leaps, expiration = TimeZoneInfoBody._read_leap_seconds(buffer, 2, 4)

    assert expiration == datetime.max.replace(tzinfo=timezone.utc)

    body = TimeZoneInfoBody(
        transition_times=[],
        leap_second_transitions=leaps,
        time_type_infos=[TimeTypeInfo(utc_offset_secs=0, is_dst=False, abbrev_index=0)],
        time_type_indices=[],
        timezone_abbrevs="UTC\x00",
        wall_standard_flags=[0],
        is_utc_flags=[0],
        leap_second_expiration=expiration,
    )

    # Should not raise OverflowError when locating leap seconds
    assert body.find_leap_second_index(datetime.max.replace(tzinfo=timezone.utc)) == 1


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


def test_resolve_preserves_fold_for_ambiguous_instants():
    tz_info = TimeZoneInfo.read("America/New_York")
    zone = ZoneInfo("America/New_York")

    first_occurrence = datetime(2023, 11, 5, 1, 30, tzinfo=zone)
    second_occurrence = first_occurrence.replace(fold=1)

    first_res = tz_info.resolve(first_occurrence)
    second_res = tz_info.resolve(second_occurrence)

    assert first_res.utc_offset_secs == -4 * 3600
    assert second_res.utc_offset_secs == -5 * 3600


def test_dst_difference_handles_non_hour():
    tz_info = TimeZoneInfo.read("Australia/Lord_Howe")
    diffs = {
        transition.dst_difference_secs
        for transition in tz_info.body.transitions
        if transition.is_dst
    }
    assert 30 * 60 in diffs


def test_read_invalid_timezone():
    with pytest.raises(FileNotFoundError):
        TimeZoneInfo.read("Invalid/Timezone")


def test_read_rejects_path_traversal():
    with pytest.raises(ValueError):
        TimeZoneInfo.read("../etc/passwd")
    with pytest.raises(ValueError):
        TimeZoneInfo.read("/absolute/path")


def test_pythontzpath_allows_relative_paths(monkeypatch, tmp_path):
    src = "/usr/share/zoneinfo/Etc/UTC"
    etc_dir = tmp_path / "relative_zones" / "Etc"
    etc_dir.mkdir(parents=True)
    dest = etc_dir / "UTC"
    shutil.copy(src, dest)

    rel_root = os.path.relpath(tmp_path / "relative_zones", os.getcwd())
    monkeypatch.setenv("PYTHONTZPATH", rel_root)

    tz_info = TimeZoneInfo.read("Etc/UTC")
    assert os.path.realpath(tz_info.filepath) == os.path.realpath(dest)


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


def test_read_timezone_without_posix_footer():
    tz_info = TimeZoneInfo.read("right/UTC")

    assert tz_info.timezone_name == "right/UTC"
    # right/* zones intentionally omit POSIX rules; ensure we tolerate this.
    assert tz_info.footer is None
    # Still usable for resolving instants
    res = tz_info.resolve(datetime(2025, 1, 1, tzinfo=timezone.utc))
    expected = (
        tz_info.body.leap_second_transitions[-1].correction
        if tz_info.body.leap_second_transitions
        else 0
    )
    assert res.utc_offset_secs == expected


def test_right_utc_leap_seconds_affect_offsets():
    tz_info = TimeZoneInfo.read("right/UTC")
    before = tz_info.resolve(
        datetime(1972, 6, 30, 23, 59, 30, tzinfo=timezone.utc)
    )
    after = tz_info.resolve(datetime(1972, 7, 1, 0, 0, 30, tzinfo=timezone.utc))

    first_correction = tz_info.body.leap_second_transitions[0].correction
    assert before.utc_offset_secs == 0
    assert after.utc_offset_secs == first_correction


def test_right_utc_next_transition_reports_leap():
    tz_info = TimeZoneInfo.read("right/UTC")
    res = tz_info.resolve(datetime(1972, 6, 30, 23, 59, 30, tzinfo=timezone.utc))
    first_leap = tz_info.body.leap_second_transitions[0].transition_time
    expected = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        seconds=first_leap
    )
    assert res.next_transition == expected


def test_resolve_drops_leap_correction_after_expiration():
    tz_info = _leap_expiring_timezone()
    expiration = tz_info.body.leap_second_expiration
    assert expiration is not None

    before = expiration - timedelta(seconds=1)
    after = expiration

    assert tz_info.resolve(before).utc_offset_secs == 1
    assert tz_info.resolve(after).utc_offset_secs == 0


def test_resolve_uses_posix_footer_without_transitions():
    tz_info = _posix_only_timezone()

    winter = datetime(2025, 1, 15, tzinfo=timezone.utc)
    summer = datetime(2025, 6, 15, tzinfo=timezone.utc)

    winter_res = tz_info.resolve(winter)
    assert winter_res.utc_offset_secs == -5 * 3600
    assert winter_res.is_dst is False
    assert winter_res.abbreviation == "STD"

    summer_res = tz_info.resolve(summer)
    assert summer_res.utc_offset_secs == -4 * 3600
    assert summer_res.is_dst is True
    assert summer_res.abbreviation == "DST"
    assert summer_res.dst_difference_secs == 3600


def test_resolve_preserves_microseconds_through_cache():
    tz_info = _posix_only_timezone()
    dt_first = datetime(2025, 1, 15, 0, 0, 0, 123456, tzinfo=timezone.utc)
    dt_second = dt_first.replace(microsecond=999999)

    first = tz_info.resolve(dt_first)
    second = tz_info.resolve(dt_second)

    assert first.resolution_time == dt_first
    expected_first_local = (dt_first + timedelta(seconds=first.utc_offset_secs)).replace(
        tzinfo=None
    )
    assert first.local_time == expected_first_local

    assert second.resolution_time == dt_second
    expected_second_local = (
        dt_second + timedelta(seconds=second.utc_offset_secs)
    ).replace(tzinfo=None)
    assert second.local_time == expected_second_local
    assert second.utc_offset_secs == first.utc_offset_secs


def test_read_all():
    timezones = available_timezones()

    for timezone_name in timezones:
        tz_info = TimeZoneInfo.read(timezone_name)

        assert tz_info.timezone_name == timezone_name
        expected_path = os.path.join("/usr/share/zoneinfo", *timezone_name.split("/"))
        assert os.path.realpath(tz_info.filepath) == os.path.realpath(expected_path)
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

        assert (
            len(tz_info.body.leap_second_transitions)
            == tz_info.header.leap_second_transitions_count
        )


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


def test_footer_transition_boundaries_match_zoneinfo():
    tz = "America/New_York"
    tz_info = TimeZoneInfo.read(tz)
    z = ZoneInfo(tz)

    last_year = tz_info.body.transitions[-1].transition_time_utc.year
    # Pick a year that is guaranteed to be served purely from the POSIX footer.
    future_year = last_year + 3
    transitions = _zoneinfo_transitions_in_year(z, future_year)
    assert len(transitions) >= 2

    for transition in transitions[:2]:
        before = transition - timedelta(seconds=1)
        after = transition + timedelta(seconds=1)

        before_res = tz_info.resolve(before)
        assert before_res.next_transition == transition

        for instant in (before, transition, after):
            expected = instant.astimezone(z).replace(tzinfo=None)
            got = tz_info.resolve(instant).local_time
            assert got == expected, f"Mismatch at {instant} for {tz}"


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
    last = body.transitions[-1]
    # Pick a UTC instant comfortably after the last TZif body transition
    dt_utc = last.transition_time_utc + timedelta(days=365)

    res = tzinfo.resolve(dt_utc)

    # We should now be in the "POSIX footer" regime, so next_transition should
    # come from the footer rules.
    assert res.next_transition is not None

    z = ZoneInfo("America/New_York")
    expected_next = _find_next_zoneinfo_transition(z, dt_utc)
    assert expected_next is not None

    assert res.next_transition == expected_next
    # Sanity: it’s in the future relative to the query instant
    assert res.next_transition > dt_utc.replace(tzinfo=timezone.utc)


def test_timezone_abbrevs_include_midstring_indices():
    body = TimeZoneInfoBody(
        transition_times=[],
        leap_second_transitions=[],
        time_type_infos=[
            TimeTypeInfo(utc_offset_secs=0, is_dst=False, abbrev_index=0),
            TimeTypeInfo(utc_offset_secs=0, is_dst=False, abbrev_index=4),
            TimeTypeInfo(utc_offset_secs=0, is_dst=True, abbrev_index=5),
        ],
        time_type_indices=[],
        timezone_abbrevs="LMT\x00AHST\x00HDT\x00",
        wall_standard_flags=[0, 0, 0],
        is_utc_flags=[0, 0, 0],
    )

    # ensure the embedded 'HST' (offset 5) is surfaced even though it falls within another label
    assert body.timezone_abbrevs == ["LMT", "AHST", "HST"]
