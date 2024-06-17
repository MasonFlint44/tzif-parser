from datetime import datetime, timedelta, timezone

import pytest

from tzif_parser import TimeZoneInfo


@pytest.mark.parametrize(
    "timezone_name, dst_transition_count, dst_offset, std_offset, dst_abbrev, std_abbrev, dst_start_utc, std_start_utc",
    [
        (
            "America/New_York",
            236,
            -4,
            -5,
            "EDT",
            "EST",
            datetime(2024, 3, 10, 6, 0, 0, 0, timezone.utc),
            datetime(2024, 11, 3, 7, 0, 0, 0, timezone.utc),
        ),
        (
            "America/Chicago",
            236,
            -5,
            -6,
            "CDT",
            "CST",
            datetime(2024, 3, 10, 7, 0, 0, 0, timezone.utc),
            datetime(2024, 11, 3, 8, 0, 0, 0, timezone.utc),
        ),
        (
            "America/Denver",
            158,
            -6,
            -7,
            "MDT",
            "MST",
            datetime(2024, 3, 10, 8, 0, 0, 0, timezone.utc),
            datetime(2024, 11, 3, 9, 0, 0, 0, timezone.utc),
        ),
        (
            "America/Los_Angeles",
            186,
            -7,
            -8,
            "PDT",
            "PST",
            datetime(2024, 3, 10, 9, 0, 0, 0, timezone.utc),
            datetime(2024, 11, 3, 10, 0, 0, 0, timezone.utc),
        ),
    ],
)
def test_read(
    timezone_name,
    dst_transition_count,
    dst_offset,
    std_offset,
    dst_abbrev,
    std_abbrev,
    dst_start_utc,
    std_start_utc,
):
    std_checkpoint_time = datetime(2024, 1, 2, 3, 4, 5, 6, timezone.utc)
    dst_checkpoint_time = datetime(2024, 6, 5, 4, 3, 2, 1, timezone.utc)
    tz_info = TimeZoneInfo.read(timezone_name)

    assert tz_info.timezone_name == timezone_name
    assert tz_info.timezone_dir == "/usr/share/zoneinfo"
    assert tz_info.version == 2
    assert len(tz_info.dst_transitions) == dst_transition_count
    assert len(tz_info.leap_second_transitions) == 0

    def validate_transition(
        checkpoint_time, is_dst, abbrev, dst_adjustment, utc_offset, transition_time_utc
    ):
        next_dst_transition = next(
            (
                transition
                for transition in tz_info.dst_transitions
                if transition.transition_time > checkpoint_time
            ),
            None,
        )

        assert next_dst_transition is not None
        assert next_dst_transition.is_dst is is_dst
        assert next_dst_transition.abbreviation == abbrev
        assert next_dst_transition.dst_adjustment == timedelta(hours=dst_adjustment)
        assert next_dst_transition.dst_adjustment_hours == dst_adjustment
        assert next_dst_transition.utc_offset == timedelta(hours=utc_offset)
        assert next_dst_transition.utc_offset_hours == utc_offset
        assert next_dst_transition.transition_time == transition_time_utc.astimezone(
            timezone(timedelta(hours=utc_offset))
        )
        assert (
            next_dst_transition.transition_time_local
            == transition_time_utc.astimezone(timezone(timedelta(hours=utc_offset)))
        )
        assert next_dst_transition.transition_time_utc == transition_time_utc

    validate_transition(
        std_checkpoint_time, True, dst_abbrev, -1, dst_offset, dst_start_utc
    )
    # TODO:
    validate_transition(
        dst_checkpoint_time, False, std_abbrev, 1, std_offset, std_start_utc
    )
