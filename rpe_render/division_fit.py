"""Experimental fitting of non-power-of-two official chart divisions."""

from __future__ import annotations

from collections import defaultdict
from math import isclose

from .models import ChartData
from .timeline import map_line_beat

FIT_TOLERANCE_BEATS = 1.0 / 16.0  # 64th-note tolerance
MIN_INTERVALS = 3
MIN_SPAN_BEATS = 0.5
MAX_DIVISION_DENOMINATOR = 128
MAX_SEQUENCE_INTERVALS = 128


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def _is_exact_native_interval(interval: float) -> bool:
    """Whether an interval is already an exact power-of-two note value."""
    if interval <= 0.0:
        return False
    division = round(4.0 / interval)
    return _is_power_of_two(division) and isclose(
        interval, 4.0 / division, rel_tol=0.0, abs_tol=1e-12
    )


def _candidate_division(times: list[float], start: int, end: int) -> float | None:
    """Return a non-power-of-two fitted interval for an exact time window."""
    interval_count = end - start
    span = times[end] - times[start]
    if interval_count < MIN_INTERVALS or span < MIN_SPAN_BEATS:
        return None
    division = round(4.0 * interval_count / span)
    if (
        division < 3
        or division > MAX_DIVISION_DENOMINATOR
        or _is_power_of_two(division)
    ):
        return None
    interval = 4.0 / division
    raw_intervals = [
        times[index + 1] - times[index] for index in range(start, end)
    ]
    # An exact supported interval is a hard rhythm boundary.  Without this
    # guard, a neighbouring 24th-note run can absorb 16th/32nd notes because
    # their numeric difference still falls inside the intentionally generous
    # 1/16-beat approximation tolerance.
    if any(_is_exact_native_interval(value) for value in raw_intervals):
        return None
    if abs(span - interval_count * interval) > FIT_TOLERANCE_BEATS:
        return None
    if any(
        abs(value - interval) > FIT_TOLERANCE_BEATS for value in raw_intervals
    ):
        return None

    # Preserve the sequence's actual boundary.  Special divisions such as
    # 10ths may start on an integer beat that is not itself a global multiple
    # of 4/10, so snapping the anchor to the fitted interval would be wrong.
    anchor = times[start]
    if any(
        abs((anchor + (index - start) * interval) - times[index])
        > FIT_TOLERANCE_BEATS
        for index in range(start, end + 1)
    ):
        return None
    return interval


def _fit_time_sequence(times: list[float]) -> dict[float, float]:
    """Find maximal contiguous fitted runs among sorted unique beat times."""
    if len(times) < MIN_INTERVALS + 1:
        return {}

    mapping: dict[float, float] = {}
    start = 0
    while start + MIN_INTERVALS < len(times):
        best_end: int | None = None
        best_interval: float | None = None
        end_limit = min(len(times), start + MAX_SEQUENCE_INTERVALS + 1)
        for end in range(start + MIN_INTERVALS, end_limit):
            candidate = _candidate_division(times, start, end)
            if candidate is not None:
                best_end, best_interval = end, candidate
        if best_end is None or best_interval is None:
            start += 1
            continue
        anchor = times[start]
        for index in range(start, best_end + 1):
            mapping[times[index]] = anchor + (index - start) * best_interval
        start = best_end + 1
    return mapping


def fit_official_divisions(chart: ChartData) -> int:
    """Fit eligible Tap/Hold starts in-place and return changed Note count.

    Drag and Flick starts are intentionally ignored.  Notes sharing one
    original mapped beat are fitted together, preserving simultaneous groups.
    The chart is mutated only when the caller explicitly enables this feature.
    """
    events: dict[float, list[tuple[object, object]]] = defaultdict(list)
    for line in chart.judge_line_list:
        for note in line.notes:
            if note.type not in (1, 2):
                continue
            display_beat = map_line_beat(line, note.start_time_beat)
            events[display_beat].append((line, note))

    mapping = _fit_time_sequence(sorted(events))
    changed = 0
    for original_beat, fitted_beat in mapping.items():
        if isclose(original_beat, fitted_beat, rel_tol=0.0, abs_tol=1e-12):
            continue
        for line, note in events[original_beat]:
            note.start_time_beat = fitted_beat / float(line.bpm_factor)
            changed += 1
    return changed


__all__ = ["fit_official_divisions"]
