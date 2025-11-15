# Copilot Instructions for tzif-parser

## Project Overview
- **tzif-parser** is a Python library for parsing Time Zone Information Format (TZif) files, extracting transitions, offsets, and POSIX time zone strings.
- Main code is in `tzif_parser/` (core parsing, models, logic) and `my_zoneinfo/` (zoneinfo compatibility/shims for Python's zoneinfo).
- Tests are in `tests/` and use `pytest` conventions.

## Architecture & Key Components
- **TZif Parsing:**
  - `tzif_parser/tzif.py`, `tzif_header.py`, `tzif_body.py`, `tz_transition.py` implement the parsing logic for TZif files.
  - `models.py` defines core data structures (e.g., `TimeZoneInfo`, `TimeZoneInfoHeader`, `TimeZoneInfoBody`, `TimeZoneTransition`, `PosixTzInfo`).
  - `posix.py` parses POSIX time zone strings.
- **POSIX Footer:**
  - TZif files include a POSIX time zone string as their footer, parsed and exposed via `PosixTzInfo`.
- **Zoneinfo Integration:**
  - `my_zoneinfo/zoneinfo.py` provides a drop-in replacement for Python's zoneinfo, using tzif-parser under the hood.
  - The shim allows access to transitions and private variables in ZoneInfo for testing, which are not available in the standard C implementation.
  - `_tzpath.py` and `_common.py` handle zoneinfo file lookup and shared utilities.

## Developer Workflows
- **Testing:**
  - Run all tests: `pytest tests/`
  - Test files: `tests/test_tzif.py`, `tests/test_posix.py`, `tests/test_tzif_perf.py`
-  - Tests may refer to private variables in ZoneInfo, which is possible via the shim but not the C implementation.
- **Build/Install:**
  - Standard Python packaging: `setup.py`, `pyproject.toml`, `requirements.txt`
  - Install locally: `pip install -e .`
- **Debugging:**
  - Use test cases for sample TZif files and POSIX strings.
  - Key entrypoint for manual parsing: `TimeZoneInfo.read(path_or_zone_name)`

## Project-Specific Patterns & Conventions
- **Data Model:**
  - All parsed TZif data is represented by `TimeZoneInfo` and its subcomponents.
  - Transitions and offsets are always exposed in both UTC and local time.
-  - The POSIX time zone string is always stored as the footer of the TZif file.
- **File Structure:**
  - Parsing logic is split by TZif file sections (header/body/footer) for clarity and maintainability.
  - POSIX string parsing is isolated in `posix.py`.
- **Zoneinfo Compatibility:**
  - `my_zoneinfo/zoneinfo.py` mimics the standard library API, but uses tzif-parser for file reading.
  - `_tzpath.py` abstracts zoneinfo file location logic for portability.

## Integration Points
- No external APIs; only standard library and local file access.
- Designed to be compatible with Python's zoneinfo interface for drop-in usage.

## Examples
- Parse a zoneinfo file:
  ```python
  from tzif_parser import TimeZoneInfo
  tz = TimeZoneInfo.read("America/New_York")
  print(tz.header, tz.body, tz.footer)
  ```
- Resolve time zone info for a datetime:
  ```python
  from tzif_parser import TimeZoneInfo
  tz = TimeZoneInfo.read("America/New_York")
  result = tz.resolve(datetime.now())
  print(result)  # TimeZoneResolution for the provided datetime
  ```
- Use zoneinfo shim:
  ```python
  from my_zoneinfo import ZoneInfo
  tz = ZoneInfo("America/New_York")
  ```

## References
- See `README.md` for API details and usage examples.
- Key files: `tzif_parser/tzif.py`, `tzif_parser/models.py`, `my_zoneinfo/zoneinfo.py`, `tests/`

---

If any conventions or workflows are unclear, please ask for clarification or provide feedback to improve these instructions.