"""谱面左右镜像（mirror_chart）单元测试。"""

import pytest

from rpe_render.easing.event_evaluator import judge_line_pose_at
from rpe_render.mirror import mirror_chart
from rpe_render.models import (
    ChartData,
    EventData,
    EventLayer,
    JudgeLineData,
    MetaData,
    NoteData,
)


def make_event(
    start: float = 0.0,
    end: float = 100.0,
    start_time=(0, 0, 1),
    end_time=(16, 0, 1),
) -> EventData:
    return EventData(
        bezier=False,
        bezier_points=[0.0, 0.0, 0.0, 0.0],
        easing_left=0.0,
        easing_right=1.0,
        easing_type=1,
        start=start,
        end=end,
        start_time=list(start_time),
        end_time=list(end_time),
        linkgroup=0,
    )


def make_note(position_x: float, note_type: int = 1) -> NoteData:
    return NoteData(
        type=note_type,
        start_time_beat=0.0,
        end_time_beat=0.0,
        position_x=position_x,
    )


def make_line(
    notes=(),
    move_x=(),
    move_y=(),
    rotate=(),
    alpha=(),
    speed=(),
    father: int = -1,
) -> JudgeLineData:
    layer = EventLayer(
        move_x_events=list(move_x),
        move_y_events=list(move_y),
        rotate_events=list(rotate),
        alpha_events=list(alpha),
        speed_events=list(speed),
    )
    return JudgeLineData(
        name="L",
        group=0,
        texture="",
        father=father,
        z_order=0,
        is_cover=False,
        bpm_factor=1.0,
        notes=list(notes),
        event_layers=[layer, EventLayer(), EventLayer(), EventLayer()],
    )


def make_chart(lines) -> ChartData:
    meta = MetaData(
        rpe_version=170,
        background="",
        charter="",
        composer="",
        chart_id="",
        level="",
        name="",
        offset=0,
        song="",
    )
    return ChartData(
        bpm_list=[],
        meta=meta,
        judge_line_group=[],
        judge_line_list=list(lines),
    )


class TestMirrorChart:
    def test_note_positions_negated(self):
        chart = make_chart(
            [make_line(notes=[make_note(100.0), make_note(-200.0), make_note(0.0)])]
        )
        mirror_chart(chart)
        positions = [note.position_x for note in chart.judge_line_list[0].notes]
        assert positions == [-100.0, 200.0, 0.0]

    def test_move_x_events_negated_across_layers(self):
        chart = make_chart(
            [
                make_line(
                    move_x=[make_event(start=10.0, end=50.0)],
                ),
                make_line(move_x=[make_event(start=-30.0, end=0.0)]),
            ]
        )
        mirror_chart(chart)
        first = chart.judge_line_list[0].event_layers[0].move_x_events[0]
        second = chart.judge_line_list[1].event_layers[0].move_x_events[0]
        assert (first.start, first.end) == (-10.0, -50.0)
        assert (second.start, second.end) == (30.0, 0.0)

    def test_rotate_events_negated(self):
        chart = make_chart([make_line(rotate=[make_event(start=45.0, end=-60.0)])])
        mirror_chart(chart)
        event = chart.judge_line_list[0].event_layers[0].rotate_events[0]
        assert (event.start, event.end) == (-45.0, 60.0)

    def test_other_events_and_times_untouched(self):
        line = make_line(
            notes=[make_note(100.0)],
            move_y=[make_event(start=1.0, end=2.0)],
            alpha=[make_event(start=0.0, end=255.0)],
            speed=[make_event(start=1.0, end=1.0)],
        )
        chart = make_chart([line])
        note = chart.judge_line_list[0].notes[0]
        before = (
            note.start_time_beat,
            note.end_time_beat,
            [event.start for event in line.event_layers[0].move_y_events],
            [event.end for event in line.event_layers[0].alpha_events],
            [event.start for event in line.event_layers[0].speed_events],
        )
        mirror_chart(chart)
        after = (
            note.start_time_beat,
            note.end_time_beat,
            [event.start for event in line.event_layers[0].move_y_events],
            [event.end for event in line.event_layers[0].alpha_events],
            [event.start for event in line.event_layers[0].speed_events],
        )
        assert before == after

    def test_double_mirror_is_identity(self):
        chart = make_chart(
            [
                make_line(
                    notes=[make_note(120.0)],
                    move_x=[make_event(start=10.0, end=50.0)],
                    rotate=[make_event(start=30.0, end=-15.0)],
                )
            ]
        )
        snapshot = make_chart(
            [
                make_line(
                    notes=[make_note(120.0)],
                    move_x=[make_event(start=10.0, end=50.0)],
                    rotate=[make_event(start=30.0, end=-15.0)],
                )
            ]
        )
        mirror_chart(chart)
        mirror_chart(chart)
        assert chart.judge_line_list[0].notes[0].position_x == (
            snapshot.judge_line_list[0].notes[0].position_x
        )
        original_layer = snapshot.judge_line_list[0].event_layers[0]
        mirrored_layer = chart.judge_line_list[0].event_layers[0]
        for kind in ("move_x_events", "rotate_events"):
            for a, b in zip(
                getattr(original_layer, kind), getattr(mirrored_layer, kind)
            ):
                assert (a.start, a.end) == (b.start, b.end)

    def test_parented_line_world_x_mirrors_exactly(self):
        """父线旋转时子线世界坐标也必须精确镜像。

        父线角度经由 sin 项进入子线世界坐标：只取反 moveX 不够，
        rotate 必须一并取反。该用例锁定这一几何性质。
        """
        parent = make_line(
            move_x=[make_event(start=100.0, end=100.0)],
            rotate=[make_event(start=30.0, end=30.0)],
        )
        child = make_line(
            father=0,
            move_x=[make_event(start=200.0, end=200.0)],
            rotate=[make_event(start=-10.0, end=-10.0)],
        )
        chart = make_chart([parent, child])
        pose_before = judge_line_pose_at(chart, 1, 0.0)

        mirror_chart(chart)
        pose_after = judge_line_pose_at(chart, 1, 0.0)

        assert pose_after.x == pytest.approx(-pose_before.x)
        assert pose_after.y == pytest.approx(pose_before.y)
        assert pose_after.angle == pytest.approx(-pose_before.angle)

    def test_root_line_note_world_x_mirrors(self):
        line = make_line(
            notes=[make_note(80.0)],
            move_x=[make_event(start=-50.0, end=-50.0)],
            rotate=[make_event(start=45.0, end=45.0)],
        )
        chart = make_chart([line])
        line_obj = chart.judge_line_list[0]
        import math

        x_before = judge_line_pose_at(chart, 0, 0.0).x + 80.0 * math.cos(
            math.radians(judge_line_pose_at(chart, 0, 0.0).angle)
        )
        mirror_chart(chart)
        pose = judge_line_pose_at(chart, 0, 0.0)
        x_after = pose.x + line_obj.notes[0].position_x * math.cos(
            math.radians(pose.angle)
        )
        assert x_after == pytest.approx(-x_before)


class TestMirrorConfigPlumbing:
    def test_render_config_default_off(self):
        from rpe_render.renderer import RenderConfig

        config = RenderConfig(chart_path="dummy.json")
        assert config.mirror is False

    def test_render_config_accepts_mirror(self):
        from rpe_render.renderer import RenderConfig

        config = RenderConfig(chart_path="dummy.json", mirror=True)
        assert config.mirror is True

    def test_cli_mirror_flag(self):
        from rpe_render.cli import parse_args

        config = parse_args(["chart.json", "--mirror"])
        assert config.mirror is True
        config = parse_args(["chart.json"])
        assert config.mirror is False
