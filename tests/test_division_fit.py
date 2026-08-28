from types import SimpleNamespace

import pytest

from rpe_render.chart_parser import parse_chart
from rpe_render.division_fit import fit_official_divisions
from rpe_render.models import ChartData, NoteData
from rpe_render.timeline import map_line_beat


def note(note_type: int, beat: float) -> NoteData:
    return NoteData(
        type=note_type,
        start_time_beat=beat,
        end_time_beat=beat,
        position_x=0.0,
    )


def test_fits_three_intervals_to_twelfth():
    line = SimpleNamespace(
        bpm_factor=1.0,
        notes=[note(1, value) for value in (0.0, 11 / 32, 21 / 32, 1.0)],
    )
    chart = ChartData([], SimpleNamespace(), [], [line])
    assert fit_official_divisions(chart) == 2
    assert [n.start_time_beat for n in line.notes] == pytest.approx(
        [0.0, 1 / 3, 2 / 3, 1.0]
    )


def test_native_power_of_two_division_is_unchanged():
    line = SimpleNamespace(
        bpm_factor=1.0,
        notes=[note(1, value) for value in (0.0, 0.25, 0.5, 0.75, 1.0)],
    )
    chart = ChartData([], SimpleNamespace(), [], [line])
    assert fit_official_divisions(chart) == 0


def test_drag_and_flick_are_not_fitted():
    line = SimpleNamespace(
        bpm_factor=1.0,
        notes=[note(kind, value) for kind, value in ((3, 0.0), (3, 11 / 32), (3, 21 / 32), (4, 1.0))],
    )
    chart = ChartData([], SimpleNamespace(), [], [line])
    before = [n.start_time_beat for n in line.notes]
    assert fit_official_divisions(chart) == 0
    assert [n.start_time_beat for n in line.notes] == before


def test_at_chart_221_to_232_fits_to_24th():
    chart = parse_chart("chart/AT.json")
    before = sorted(
        {
            map_line_beat(line, item.start_time_beat)
            for line in chart.judge_line_list
            for item in line.notes
            if item.type == 1 and 221 <= map_line_beat(line, item.start_time_beat) <= 232
        }
    )
    fit_official_divisions(chart)
    after = sorted(
        {
            map_line_beat(line, item.start_time_beat)
            for line in chart.judge_line_list
            for item in line.notes
            if item.type == 1 and 221 <= map_line_beat(line, item.start_time_beat) <= 232
        }
    )
    assert len(before) == len(after) == 67
    assert after == pytest.approx([221 + index / 6 for index in range(67)])


def test_rrharil_keeps_division_boundaries_stable():
    chart = parse_chart("chart/Rrharil.json")
    fit_official_divisions(chart)
    values = sorted(
        {
            map_line_beat(line, item.start_time_beat)
            for line in chart.judge_line_list
            for item in line.notes
            if item.type == 1 and 388 <= map_line_beat(line, item.start_time_beat) <= 391.5
        }
    )
    intervals = [values[index + 1] - values[index] for index in range(len(values) - 1)]
    assert intervals == pytest.approx(
        [1 / 4, 1 / 4] + [1 / 6] * 6 + [1 / 8] * 8 + [1 / 6] * 6
    )


def test_opia_special_tenth_division():
    chart = parse_chart("chart/opia.json")
    fit_official_divisions(chart)
    values = sorted(
        {
            map_line_beat(line, item.start_time_beat)
            for line in chart.judge_line_list
            for item in line.notes
            if item.type == 1 and 365 <= map_line_beat(line, item.start_time_beat) <= 367
        }
    )
    assert values == pytest.approx([365 + index * 0.4 for index in range(6)])


def test_der_schneid_mixed_twelfth_and_twenty_fourth_divisions():
    chart = parse_chart("chart/DerSchneid.json")
    fit_official_divisions(chart)
    values = sorted(
        {
            map_line_beat(line, item.start_time_beat)
            for line in chart.judge_line_list
            for item in line.notes
            if item.type in (1, 2)
            and 284 <= map_line_beat(line, item.start_time_beat) <= 292
        }
    )
    grid_indices = [
        0, 2, 4, 6, 8, 10, 12, 13, 14, 15, 16, 18, 20, 22, 24, 25,
        26, 28, 30, 31, 32, 34, 36, 37, 38, 40, 42, 43, 44, 45, 46, 47,
    ]
    assert values == pytest.approx([284 + index / 6 for index in grid_indices])


def test_der_schneid_flick_anchors_following_twelfth_division():
    chart = parse_chart("chart/DerSchneid.json")
    fit_official_divisions(chart)
    values = sorted(
        {
            map_line_beat(line, item.start_time_beat)
            for line in chart.judge_line_list
            for item in line.notes
            if item.type in (1, 2, 3)
            and 376 <= map_line_beat(line, item.start_time_beat) <= 378
        }
    )
    assert values == pytest.approx([376 + index / 3 for index in range(7)])
