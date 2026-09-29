"""BPM 缩放倍率（time_scale）测试。"""

import pytest

from rpe_render.info_bar import compute_duration_seconds
from rpe_render.models import (
    BPMEvent,
    ChartData,
    EventData,
    EventLayer,
    JudgeLineData,
    MetaData,
    NoteData,
)
from rpe_render.renderer import RenderConfig
from rpe_render.time_scale import normalize_bpm_scale, scale_chart_time
from rpe_render.time_utils import timet_to_beats
from rpe_render.timeline import (
    compute_canvas_size,
    compute_columns,
    compute_max_beat,
)


def _event(start: float, end: float, value: float = 0.0) -> EventData:
    """构造覆盖 [start, end] 拍的定值事件。"""
    return EventData(
        bezier=False,
        bezier_points=[0.0, 0.0, 0.0, 0.0],
        easing_left=0.0,
        easing_right=1.0,
        easing_type=1,
        start=value,
        end=value,
        start_time=[int(start), 0, 1],
        end_time=[int(end), 0, 1],
        linkgroup=0,
    )


def _line(*, bpm_factor: float = 1.0, bpm: float = 0.0) -> JudgeLineData:
    layer = EventLayer(move_x_events=[_event(0, 100)])
    return JudgeLineData(
        name="line",
        group=0,
        texture="",
        father=-1,
        z_order=0,
        is_cover=True,
        bpm_factor=bpm_factor,
        notes=[],
        event_layers=[layer, EventLayer(), EventLayer(), EventLayer()],
        bpm=bpm,
    )


def _chart(lines: list[JudgeLineData], *, bpm: float = 120.0) -> ChartData:
    return ChartData(
        bpm_list=[BPMEvent(bpm, [0, 0, 1])],
        meta=MetaData(0, "", "", "", "", "", "", 0, ""),
        judge_line_group=[],
        judge_line_list=lines,
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1/4", 0.25),
        ("1/3", 1.0 / 3.0),
        ("1/2", 0.5),
        ("1", 1.0),
        ("2", 2.0),
        ("3", 3.0),
        ("4", 4.0),
        (0.25, 0.25),
        (1.0 / 3.0, 1.0 / 3.0),
        (2, 2.0),
        (" 1/2 ", 0.5),
    ],
)
def test_normalize_accepts_all_tiers(value, expected):
    assert normalize_bpm_scale(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [0, -1, 0.7, 5.0, "0", "-1/3", "5", "abc", "1/0", "", None],
)
def test_normalize_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        normalize_bpm_scale(value)


def test_scale_notes_and_bpm_values():
    line = _line(bpm_factor=2.0, bpm=540.0)
    tap = NoteData(1, 3.0, 3.0, 0.0, raw_start_time=[3, 0, 1])
    hold = NoteData(
        2, 1.5, 4.5, 0.0, raw_start_time=[1, 1, 2], raw_end_time=[4, 1, 2]
    )
    line.notes = [tap, hold]
    chart = _chart([line], bpm=540.0)

    scale_chart_time(chart, 1.0 / 3.0)

    assert tap.start_time_beat == pytest.approx(1.0)
    assert hold.start_time_beat == pytest.approx(0.5)
    assert hold.end_time_beat == pytest.approx(1.5)
    # 原始 TimeT 按分数精确重建：1.5×1/3=0.5、4.5×1/3=1.5
    assert tap.raw_start_time == [1, 0, 1]
    assert hold.raw_start_time == [0, 1, 2]
    assert hold.raw_end_time == [1, 1, 2]
    assert line.bpm == pytest.approx(180.0)
    # bpm_factor 是比值，缩放不变
    assert line.bpm_factor == pytest.approx(2.0)
    assert chart.bpm_list[0].bpm == pytest.approx(180.0)
    assert chart.bpm_list[0].start_time == [0, 0, 1]


def test_scale_events_and_cache_consistency():
    line = _line()
    event = line.event_layers[0].move_x_events[0]
    chart = _chart([line])

    scale_chart_time(chart, 1.0 / 3.0)

    assert event.start_time == [0, 0, 1]
    assert event.end_time == [33, 1, 3]  # 100 × 1/3 = 33.333…
    assert event.start_beat == pytest.approx(0.0)
    assert event.end_beat == pytest.approx(100.0 / 3.0)
    # 缓存拍数与缩放后的 TimeT 保持一致（与解析路径相同的不变量）
    assert event.end_beat == timet_to_beats(tuple(event.end_time))
    # 事件值（空间量）不缩放
    assert event.start == 0.0 and event.end == 0.0


def test_factor_one_is_noop():
    line = _line(bpm=540.0)
    note = NoteData(2, 4.0, 8.0, 0.0, raw_start_time=[4, 0, 1])
    line.notes = [note]
    chart = _chart([line], bpm=540.0)
    before = (
        note.start_time_beat,
        list(note.raw_start_time),
        line.bpm,
        chart.bpm_list[0].bpm,
        chart.meta.duration,
    )

    scale_chart_time(chart, 1.0)

    after = (
        note.start_time_beat,
        list(note.raw_start_time),
        line.bpm,
        chart.bpm_list[0].bpm,
        chart.meta.duration,
    )
    assert before == after


def test_scale_reduces_max_beat_and_keeps_duration():
    line = _line(bpm=540.0)
    line.notes = [NoteData(2, 4.0, 296.0, 0.0)]
    chart = _chart([line], bpm=540.0)
    assert compute_max_beat(chart) == pytest.approx(296.0)
    duration_before = compute_duration_seconds(chart)

    scale_chart_time(chart, 1.0 / 3.0)

    # 拍数与 BPM 同乘 1/3：画布拍数缩为 1/3，真实秒时长不变
    assert compute_max_beat(chart) == pytest.approx(296.0 / 3.0)
    assert compute_duration_seconds(chart) == pytest.approx(duration_before)
    # META.duration（秒）不缩放
    chart.meta.duration = 120.0
    scale_chart_time(chart, 2.0)
    assert chart.meta.duration == 120.0


def test_canvas_width_shrinks_with_scaled_chart():
    line = _line(bpm=540.0)
    line.notes = [NoteData(2, 4.0, 296.0, 0.0)]
    chart = _chart([line], bpm=540.0)
    width_before, _ = compute_canvas_size(
        compute_columns(compute_max_beat(chart), column_beats=64)
    )

    scale_chart_time(chart, 1.0 / 3.0)

    width_after, _ = compute_canvas_size(
        compute_columns(compute_max_beat(chart), column_beats=64)
    )
    # 296 拍 5 栏 → 约 98.7 拍 2 栏，画布宽度显著收缩（高度不变）
    assert width_after < width_before * 0.5


def test_render_config_validates_bpm_scale():
    with pytest.raises(ValueError):
        RenderConfig(chart_path="chart.json", bpm_scale=0.7)
    config = RenderConfig(chart_path="chart.json", bpm_scale="1/3")
    assert config.bpm_scale == pytest.approx(1.0 / 3.0)
