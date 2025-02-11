# tzif-parser

`tzif-parser` is a Python library for parsing and handling Time Zone Information Format (TZif) files. These files are used to store time zone information, including transitions, UTC offsets, and daylight saving time information.

## Features

- Parse TZif files and extract time zone information.
- Convert transition times to local wall and standard times.
- Read POSIX time zone strings.

## Installation

To install `tzif-parser`, install it from PyPI using pip:

```sh
pip install tzif-parser
```

## Usage

Here's an example of how to use `tzif-parser` to read a TZif file and extract time zone information:

```python
from tzif_parser import TimeZoneInfo

tz_info = TimeZoneInfo.read("America/New_York")

print(tz_info)
print(tz_info.header)
print(tz_info.body)
print(tz_info.footer)
```

## Classes

### `TimeZoneInfo`

Represents the time zone information parsed from a TZif file.

#### Properties

- `version`: The version of the TZif file.
- `header`: The header data of the TZif file.
- `body`: The body data of the TZif file.
- `footer`: The POSIX time zone information.

### `TimeZoneInfoHeader`

Represents the header data of a TZif file.

#### Properties

- `version`: The version of the TZif file.
- `is_utc_flag_count`: The number of UTC/local indicators.
- `wall_standard_flag_count`: The number of standard/wall indicators.
- `leap_second_transitions_count`: The number of leap second transitions.
- `transitions_count`: The number of transition times.
- `local_time_type_count`: The number of local time types.
- `timezone_abbrev_byte_count`: The number of bytes used for time zone abbreviations.

### `TimeZoneInfoBody`

Represents the body data of a TZif file.

#### Properties

- `transition_times`: The list of transition times.
- `leap_second_transitions`: The list of leap second transitions.
- `time_type_infos`: The list of time type information.
- `time_type_indices`: The list of time type indices.
- `timezone_abbrevs`: The list of time zone abbreviations.
- `wall_standard_flags`: The list of standard/wall flags.
- `is_utc_flags`: The list of UTC/local flags.
- `transitions`: The list of time zone transitions.

### `TimeZoneTransition`

Represents a single time zone transition.

#### Properties

- `transition_time_local_standard`: The local standard time of the transition.
- `transition_time_local_wall`: The local wall time of the transition.
- `transition_time_utc`: The UTC time of the transition.
- `abbreviation`: The time zone abbreviation.
- `utc_offset_secs`: The UTC offset in seconds.
- `utc_offset_hours`: The UTC offset in hours.
- `dst_offset_secs`: The DST offset in seconds.
- `dst_offset_hours`: The DST offset in hours.
- `is_dst`: Whether the transition is during daylight saving time.
- `wall_standard_flag`: The wall/standard flag.
- `is_utc`: Whether the transition time is in UTC.

### `PosixTzInfo`

Represents the POSIX time zone information.

#### Properties

- `posix_string`: The POSIX time zone string.
- `standard_abbrev`: The standard time abbreviation.
- `utc_offset_hours`: The UTC offset in hours.
- `dst_abbrev`: The daylight saving time abbreviation.
- `dst_start`: The start of daylight saving time.
- `dst_end`: The end of daylight saving time.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on GitHub.

## License

This project is licensed under the MIT License.
