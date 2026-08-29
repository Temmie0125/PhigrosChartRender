"""Experimental fitting of non-power-of-two official chart divisions."""

from __future__ import annotations

from collections import defaultdict
from math import isclose

from .models import ChartData
from .timeline import map_line_beat

FIT_TOLERANCE_BEATS = 1.0 / 16.0  # 64th-note tolerance
GRID_ALIGNMENT_TOLERANCE_BEATS = 1.0 / 64.0
MIN_INTERVALS = 3
MIN_SPAN_BEATS = 0.5
MAX_DIVISION_DENOMINATOR = 128
MAX_SEQUENCE_INTERVALS = 128
MAX_GRID_STEP = 2


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
    """Return the coarsest non-power-of-two grid fitting a time window."""
    interval_count = end - start
    span = times[end] - times[start]
    if interval_count < MIN_INTERVALS or span < MIN_SPAN_BEATS:
        return None
    raw_intervals = [
        times[index + 1] - times[index] for index in range(start, end)
    ]
    # An exact supported interval is a hard rhythm boundary.  Without this
    # guard, a neighbouring 24th-note run can absorb 16th/32nd notes because
    # their numeric difference still falls inside the intentionally generous
    # 1/16-beat approximation tolerance.
    # A frequent official pattern is ``24th jump, 12th, native 8th``.  The
    # final native interval is a rhythmic boundary (the half-beat anchor),
    # not part of the approximated grid.  Keep it as an endpoint while
    # fitting the two preceding intervals.  Native intervals in the middle
    # of a candidate remain hard boundaries unless they form a single native
    # half-beat bridge between non-native intervals (e.g. Doll at beat 82:
    # 12th, 8th, 24th).  That bridge is three fitted 24th grid steps and is
    # still an exact native boundary, so allowing it does not move the anchor.
    trailing_native = _is_exact_native_interval(raw_intervals[-1])
    fit_intervals = raw_intervals[:-1] if trailing_native else raw_intervals
    if len(fit_intervals) < (MIN_INTERVALS - 1 if trailing_native else MIN_INTERVALS):
        return None
    native_indices = [
        index for index, value in enumerate(fit_intervals)
        if _is_exact_native_interval(value)
    ]
    if native_indices:
        # Only an internal half-beat may bridge two approximated intervals;
        # other native intervals remain hard boundaries as in the old logic.
        if any(
            value != 0.5
            for value in (fit_intervals[index] for index in native_indices)
        ) or any(index == 0 or index == len(fit_intervals) - 1 for index in native_indices):
            return None
    fit_end = start + len(fit_intervals)
    fit_span = times[fit_end] - times[start]
    if fit_span < MIN_SPAN_BEATS:
        return None

    # Preserve the sequence's actual boundary.  Special divisions such as
    # 10ths may start on an integer beat that is not itself a global multiple
    # of 4/10, so snapping the anchor to the fitted interval would be wrong.
    anchor = times[start]
    for division in range(3, MAX_DIVISION_DENOMINATOR + 1):
        if _is_power_of_two(division):
            continue
        interval = 4.0 / division
        grid_steps = [round(value / interval) for value in fit_intervals]
        if any(
            step < 1
            or step > MAX_GRID_STEP
            and not (
                _is_exact_native_interval(value)
                and step == MAX_GRID_STEP + 1
            )
            for value, step in zip(fit_intervals, grid_steps)
        ):
            continue
        if any(
            abs(value - step * interval) > FIT_TOLERANCE_BEATS
            for value, step in zip(fit_intervals, grid_steps)
        ):
            continue
        if any(
            abs(
                anchor
                + round((times[index] - anchor) / interval) * interval
                - times[index]
            )
            > GRID_ALIGNMENT_TOLERANCE_BEATS
            for index in range(start, end + 1)
        ):
            continue
        return interval
    return None


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
            grid_index = round((times[index] - anchor) / best_interval)
            mapping[times[index]] = anchor + grid_index * best_interval
        # Reuse the last note as the next run's anchor. Adjacent rhythm runs
        # commonly share a boundary beat, and skipping it can leave the first
        # few approximated notes of the following run unfitted.
        start = best_end
    return mapping


def fit_official_divisions(chart: ChartData) -> int:
    """Fit eligible Tap/Hold starts in-place and return changed Note count.

    Drag and Flick starts may anchor a fitted grid but are never moved. Notes
    sharing one original mapped beat are fitted together, preserving
    simultaneous groups. The chart is mutated only when the caller explicitly
    enables this feature.
    """
    events: dict[float, list[tuple[object, object]]] = defaultdict(list)
    rhythm_times: set[float] = set()
    for line in chart.judge_line_list:
        for note in line.notes:
            display_beat = map_line_beat(line, note.start_time_beat)
            rhythm_times.add(display_beat)
            if note.type not in (1, 2):
                continue
            events[display_beat].append((line, note))

    mapping = _fit_time_sequence(sorted(rhythm_times))
    changed = 0
    for original_beat, fitted_beat in mapping.items():
        if isclose(original_beat, fitted_beat, rel_tol=0.0, abs_tol=1e-12):
            continue
        for line, note in events.get(original_beat, ()):
            note.start_time_beat = fitted_beat / float(line.bpm_factor)
            changed += 1
    return changed


__all__ = ["fit_official_divisions"]
