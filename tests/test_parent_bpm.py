"""父线坐标系与 BPM 因数适配测试。"""

import json

import pytest

from rpe_render.chart_parser import parse_chart
from rpe_render.easing.event_evaluator import judge_line_pose_at
from rpe_render.models import (
    EventData,
    EventLayer,
    JudgeLineData,
    NoteData,
    NoteRenderInfo,
)
from rpe_render.note_renderer import detect_multitap_groups_at_beats
from rpe_render.timeline import compute_max_beat, map_line_beat


def _event(start: float, end: float, value: float) -> EventData:
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


def _line(*, father: int = -1, x: float = 0.0, y: float = 0.0,
          angle: float = 0.0, rotate_with_father: bool = True,
          bpm_factor: float = 1.0) -> JudgeLineData:
    layer = EventLayer(
        move_x_events=[_event(0, 100, x)],
        move_y_events=[_event(0, 100, y)],
        rotate_events=[_event(0, 100, angle)],
    )
    return JudgeLineData(
        name="line",
        group=0,
        texture="",
        father=father,
        z_order=0,
        is_cover=True,
        bpm_factor=bpm_factor,
        notes=[],
        event_layers=[layer, EventLayer(), EventLayer(), EventLayer()],
        rotate_with_father=rotate_with_father,
    )


def test_parent_pose_uses_move_y_and_inherits_rotation():
    from rpe_render.models import ChartData, MetaData, BPMEvent

    chart = ChartData(
        bpm_list=[BPMEvent(120.0, [0, 0, 1])],
        meta=MetaData(0, "", "", "", "", "", "", 0, ""),
        judge_line_group=[],
        judge_line_list=[
            _line(x=100, y=50, angle=90),
            _line(father=0, x=10, y=20, angle=30),
        ],
    )

    pose = judge_line_pose_at(chart, 1, 4.0)
    assert pose.x == pytest.approx(80.0)
    assert pose.y == pytest.approx(60.0)
    assert pose.angle == pytest.approx(120.0)


def test_rotate_with_father_only_controls_child_angle():
    from rpe_render.models import ChartData, MetaData, BPMEvent

    chart = ChartData(
        bpm_list=[BPMEvent(120.0, [0, 0, 1])],
        meta=MetaData(0, "", "", "", "", "", "", 0, ""),
        judge_line_group=[],
        judge_line_list=[
            _line(x=0, angle=90),
            _line(father=0, x=10, y=20, angle=30, rotate_with_father=False),
        ],
    )

    pose = judge_line_pose_at(chart, 1, 4.0)
    assert pose.x == pytest.approx(-20.0)
    assert pose.angle == pytest.approx(30.0)


def test_parent_pose_synchronizes_different_bpm_factors():
    from rpe_render.models import ChartData, MetaData, BPMEvent

    # 子线 local beat=4、factor=2 对应主谱面 beat=8；父线 factor=1
    # 应在父线 beat=8 的状态求值，而不是错误地使用父线 beat=4。
    parent = _line(x=0.0, bpm_factor=1.0)
    parent.event_layers[0].move_x_events = [_event(0, 4, 0.0), _event(8, 100, 80.0)]
    child = _line(father=0, x=10.0, bpm_factor=2.0)
    chart = ChartData(
        bpm_list=[BPMEvent(120.0, [0, 0, 1])],
        meta=MetaData(0, "", "", "", "", "", "", 0, ""),
        judge_line_group=[], judge_line_list=[parent, child],
    )

    pose = judge_line_pose_at(chart, 1, 4.0)
    assert pose.x == pytest.approx(90.0)


def test_bpm_factor_expands_main_timeline():
    line = _line(bpm_factor=2.0)
    line.notes = [NoteData(1, 3.0, 4.0, 0.0)]
    from rpe_render.models import ChartData, MetaData, BPMEvent

    chart = ChartData(
        bpm_list=[BPMEvent(120.0, [0, 0, 1])],
        meta=MetaData(0, "", "", "", "", "", "", 0, ""),
        judge_line_group=[], judge_line_list=[line],
    )
    assert map_line_beat(line, 4.0) == pytest.approx(8.0)
    assert compute_max_beat(chart) == pytest.approx(8.0)


def test_multitap_uses_mapped_main_timeline():
    def info(beat):
        return NoteRenderInfo(
            note=NoteData(1, beat, beat, 0.0),
            true_x=0.0,
            beat=beat,
            end_beat=beat,
            is_multitap=False,
            judge_line_name="line",
            column=0,
            x_pixel=0.0,
            y_pixel=0.0,
            y_pixel_end=0.0,
        )

    # 不同来源线的原始拍数不同，但映射到主谱面后同刻。
    assert detect_multitap_groups_at_beats([info(4.0), info(4.0)]) == {0, 1}


def _raw_chart(lines):
    return {
        "BPMList": [{"bpm": 120, "startTime": [0, 0, 1]}],
        "META": {},
        "judgeLineList": lines,
    }


def _raw_line(*, father=-1, bpmfactor=1.0):
    return {
        "father": father,
        "bpmfactor": bpmfactor,
        "eventLayers": [None, None, None, None],
        "notes": [],
    }


def test_invalid_parent_and_factor_raise(tmp_path):
    invalid_parent = tmp_path / "invalid-parent.json"
    invalid_parent.write_text(
        json.dumps(_raw_chart([_raw_line(father=1)])), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid father index"):
        parse_chart(invalid_parent)

    invalid_factor = tmp_path / "invalid-factor.json"
    invalid_factor.write_text(
        json.dumps(_raw_chart([_raw_line(bpmfactor=0)])), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="bpmfactor"):
        parse_chart(invalid_factor)


def test_parent_cycle_raises(tmp_path):
    path = tmp_path / "cycle.json"
    path.write_text(
        json.dumps(_raw_chart([_raw_line(father=1), _raw_line(father=0)])),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="father cycle"):
        parse_chart(path)
