import logging
import statistics as stats
import time
from datetime import datetime, timedelta

from tzif_parser import TimeZoneInfo


def _percentile(values, pct):
    """
    pct in [0,100]. Uses nearest-rank after sorting.
    """
    if not values:
        return float("nan")
    if pct <= 0:
        return values[0]
    if pct >= 100:
        return values[-1]
    k = int(round((pct / 100.0) * (len(values) - 1)))
    return values[k]


def test_resolve_performance():
    # A small but diverse set of zones (DST, no-DST, fractional offsets, southern hemisphere)
    zones = [
        "America/New_York",
        "America/Chicago",
        "Europe/London",
        "Asia/Tokyo",
        "Asia/Kolkata",
        "Australia/Sydney",
        "Africa/Abidjan",  # UTC
        "Pacific/Auckland",
    ]

    # A spread of UTC instants (naive -> interpreted as UTC by your API)
    dates = [
        datetime(1900, 1, 1, 0, 0, 0),
        datetime(1950, 6, 1, 12, 0, 0),
        datetime(2000, 3, 26, 1, 59, 59),
        datetime(2024, 11, 3, 6, 59, 59),
        datetime(2025, 3, 9, 6, 59, 59),
        datetime(2039, 6, 2, 0, 0, 0),
        datetime(2060, 1, 1, 0, 0, 0),
    ]

    # How many total resolve calls to measure
    total_calls = 5000

    # load TZ data
    tz_objs = {z: TimeZoneInfo.read(z) for z in zones}

    # Time the loop
    timings = []
    start_wall = time.perf_counter()

    # Round-robin through zones x dates without extra allocations inside the loop
    idx = 0
    zones_len = len(zones)
    dates_len = len(dates)

    while idx < total_calls:
        z = zones[idx % zones_len]
        d = dates[(idx // zones_len) % dates_len]
        tzi = tz_objs[z]

        t0 = time.perf_counter()
        res = tzi.resolve(d)
        # Access a couple of fields to ensure work isn't optimized away
        _ = res.local_time, res.utc_offset_secs, res.is_dst
        t1 = time.perf_counter()

        timings.append(t1 - t0)
        idx += 1

    end_wall = time.perf_counter()

    # Stats
    timings.sort()
    total_time = end_wall - start_wall
    ops_per_sec = total_calls / total_time if total_time > 0 else float("inf")
    mean_s = stats.fmean(timings)
    median_s = timings[len(timings) // 2]
    p90_s = _percentile(timings, 90)
    p95_s = _percentile(timings, 95)
    p99_s = _percentile(timings, 99)
    min_s = timings[0]
    max_s = timings[-1]

    # Pretty print as microseconds per call
    us = lambda s: f"{s * 1e6:,.1f} μs"

    logging.debug("\n=== tzif_parser.resolve() performance ===")
    logging.debug(f"Total calls     : {total_calls:,}")
    logging.debug(f"Total wall time : {total_time:,.3f} s")
    logging.debug(f"Throughput      : {ops_per_sec:,.1f} ops/s")
    logging.debug(f"Mean            : {us(mean_s)}")
    logging.debug(f"Median          : {us(median_s)}")
    logging.debug(f"p90             : {us(p90_s)}")
    logging.debug(f"p95             : {us(p95_s)}")
    logging.debug(f"p99             : {us(p99_s)}")
    logging.debug(f"Min / Max       : {us(min_s)} / {us(max_s)}")


def test_resolve_range_cache_performance():
    """
    Performance test focused on the new range-caching behavior.

    For each zone, we:
      - Resolve a single "anchor" datetime to seed the cache.
      - Then resolve many nearby datetimes that should fall in the same
        transition / offset regime, so resolve() can use the cached
        offset/DST/abbr and only recompute local_time.
    """
    zones = [
        "America/New_York",
        "America/Chicago",
        "Europe/London",
        "Asia/Tokyo",
        "Asia/Kolkata",
        "Australia/Sydney",
        "Africa/Abidjan",  # UTC
        "Pacific/Auckland",
    ]

    # Choose a base UTC instant that is unlikely to be right at a DST boundary.
    base_dt = datetime(2024, 1, 15, 0, 0, 0)

    # How many points per zone, all clustered near base_dt
    steps_per_zone = 1000
    total_calls = steps_per_zone * len(zones)

    # Precompute per-zone datetime sequences so we don't allocate in the hot loop
    # We use 5-minute increments over ~3.5 days; for most zones this will stay
    # entirely within one offset regime, making range caching very effective.
    dates_by_zone: dict[str, list[datetime]] = {}
    for z in zones:
        dates_by_zone[z] = [
            base_dt + timedelta(minutes=5 * i) for i in range(steps_per_zone)
        ]

    tz_objs = {z: TimeZoneInfo.read(z) for z in zones}

    timings = []
    start_wall = time.perf_counter()

    for z in zones:
        tzi = tz_objs[z]
        seq = dates_by_zone[z]

        # Seed the cache with the first datetime in this sequence
        tzi.resolve(seq[0])

        for d in seq:
            t0 = time.perf_counter()
            res = tzi.resolve(d)
            # Access fields so the work is not optimized away
            _ = res.local_time, res.utc_offset_secs, res.is_dst
            t1 = time.perf_counter()
            timings.append(t1 - t0)

    end_wall = time.perf_counter()

    timings.sort()
    total_time = end_wall - start_wall
    ops_per_sec = total_calls / total_time if total_time > 0 else float("inf")
    mean_s = stats.fmean(timings)
    median_s = timings[len(timings) // 2]
    p90_s = _percentile(timings, 90)
    p95_s = _percentile(timings, 95)
    p99_s = _percentile(timings, 99)
    min_s = timings[0]
    max_s = timings[-1]

    us = lambda s: f"{s * 1e6:,.1f} μs"

    logging.debug("\n=== tzif_parser.resolve() range-cache performance ===")
    logging.debug(f"Total calls     : {total_calls:,}")
    logging.debug(f"Total wall time : {total_time:,.3f} s")
    logging.debug(f"Throughput      : {ops_per_sec:,.1f} ops/s")
    logging.debug(f"Mean            : {us(mean_s)}")
    logging.debug(f"Median          : {us(median_s)}")
    logging.debug(f"p90             : {us(p90_s)}")
    logging.debug(f"p95             : {us(p95_s)}")
    logging.debug(f"p99             : {us(p99_s)}")
    logging.debug(f"Min / Max       : {us(min_s)} / {us(max_s)}")
