"""event_evaluator 单元测试。"""

import pytest

from rpe_render.easing.event_evaluator import (
    compute_eased_progress,
    evaluate_event_value,
    find_enclosing_event,
    judge_line_rotate_at,
    judge_line_x_at,
)
from rpe_render.models import EventData, EventLayer, JudgeLineData


def make_event(
    start: float = 0.0,
    end: float = 100.0,
    start_time=(0, 0, 1),
    end_time=(16, 0, 1),
    easing_type: int = 1,
    bezier: bool = False,
    bezier_points=None,
    easing_left: float = 0.0,
    easing_right: float = 1.0,
) -> EventData:
    return EventData(
        bezier=bezier,
        bezier_points=bezier_points or [0.0, 0.0, 0.0, 0.0],
        easing_left=easing_left,
        easing_right=easing_right,
        easing_type=easing_type,
        start=start,
        end=end,
        start_time=list(start_time),
        end_time=list(end_time),
        linkgroup=0,
    )


def make_line(layers_move_x) -> JudgeLineData:
    """layers_move_x: list of moveXEvents lists（4 层）。"""
    layers = [
        EventLayer(move_x_events=events) for events in layers_move_x
    ]
    while len(layers) < 4:
        layers.append(EventLayer())
    return JudgeLineData(
        name="L",
        group=0,
        texture="",
        father=-1,
        z_order=0,
        is_cover=False,
        bpm_factor=1.0,
        notes=[],
        event_layers=layers,
    )


def make_rot_line(layers_rotate) -> JudgeLineData:
    """layers_rotate: list of rotateEvents lists（4 层）。"""
    layers = [EventLayer(rotate_events=events) for events in layers_rotate]
    while len(layers) < 4:
        layers.append(EventLayer())
    return JudgeLineData(
        name="L",
        group=0,
        texture="",
        father=-1,
        z_order=0,
        is_cover=False,
        bpm_factor=1.0,
        notes=[],
        event_layers=layers,
    )


class TestEvaluateEventValue:
    def test_linear(self):
        ev = make_event(start=0.0, end=100.0)
        assert evaluate_event_value(ev, 0.0) == 0.0
        assert evaluate_event_value(ev, 8.0) == pytest.approx(50.0)
        assert evaluate_event_value(ev, 16.0) == pytest.approx(100.0)

    def test_ease_in_quad(self):
        # easeInQuad: f(t)=t^2 → t=0.5 时 value = 0 + 100*0.25
        ev = make_event(start=0.0, end=100.0, easing_type=5)
        assert evaluate_event_value(ev, 8.0) == pytest.approx(25.0)

    def test_zero_duration_raises(self):
        ev = make_event(start_time=(4, 0, 1), end_time=(4, 0, 1))
        with pytest.raises(ValueError):
            evaluate_event_value(ev, 4.0)


class TestComputeEasedProgress:
    def test_no_clip_linear(self):
        assert compute_eased_progress(0.5, 1, 0.0, 1.0, False, []) == 0.5

    def test_unknown_type_raises(self):
        with pytest.raises(KeyError):
            compute_eased_progress(0.5, 99, 0.0, 1.0, False, [])

    def test_clip_formula(self):
        # easeInQuad (type 5): f(l=0)=0, f(r=0.5)=0.25
        # g(0.25) = (0.25-0)*f((0.25-0)/0.5)+0 = 0.25*f(0.5) = 0.0625
        got = compute_eased_progress(0.25, 5, 0.0, 0.5, False, [])
        assert got == pytest.approx(0.25 * 0.25)

    def test_result_clamped(self):
        # easeOutBack 中段会超过 1，应被 clamp
        got = compute_eased_progress(0.8, 20, 0.0, 1.0, False, [])
        assert 0.0 <= got <= 1.0

    def test_bezier(self):
        # 对角控制点 ≈ 线性
        got = compute_eased_progress(
            0.5, 1, 0.0, 1.0, True, [0.0, 0.0, 1.0, 1.0]
        )
        assert got == pytest.approx(0.5, abs=0.01)


class TestFindEnclosingEvent:
    def test_found(self):
        e1 = make_event(start_time=(0, 0, 1), end_time=(8, 0, 1))
        e2 = make_event(start_time=(8, 0, 1), end_time=(16, 0, 1))
        assert find_enclosing_event([e1, e2], 4.0) is e1
        assert find_enclosing_event([e1, e2], 12.0) is e2

    def test_boundary_belongs_to_both_returns_first(self):
        e1 = make_event(start_time=(0, 0, 1), end_time=(8, 0, 1))
        e2 = make_event(start_time=(8, 0, 1), end_time=(16, 0, 1))
        assert find_enclosing_event([e1, e2], 8.0) is e1

    def test_none(self):
        e = make_event(start_time=(10, 0, 1), end_time=(20, 0, 1))
        assert find_enclosing_event([e], 5.0) is None

    def test_empty_list(self):
        assert find_enclosing_event([], 1.0) is None


class TestJudgeLineXMultiLayer:
    def test_multi_layer_summed(self):
        layer_a = make_event(start=0.0, end=10.0)  # t=8 → 5
        layer_b = make_event(start=10.0, end=30.0)  # t=8 → 20
        line = make_line([[layer_a], [layer_b], [], []])
        assert judge_line_x_at(line, 8.0) == pytest.approx(25.0)

    def test_no_events_returns_zero(self):
        line = make_line([[], [], [], []])
        assert judge_line_x_at(line, 3.0) == 0.0

    def test_outside_coverage_ignored(self):
        ev = make_event(start=0.0, end=10.0, start_time=(4, 0, 1), end_time=(8, 0, 1))
        line = make_line([[ev], [], [], []])
        assert judge_line_x_at(line, 2.0) == 0.0


class TestJudgeLineRotate:
    """judge_line_rotate_at：4 层 rotateEvents 叠加，语义与 judge_line_x_at 一致。"""

    def test_single_layer_linear_interpolation(self):
        # [0,16] 拍内 0° → 80°，t=8 → 40°
        ev = make_event(start=0.0, end=80.0)
        line = make_rot_line([[ev], [], [], []])
        assert judge_line_rotate_at(line, 8.0) == pytest.approx(40.0)

    def test_multi_layer_summed(self):
        layer_a = make_event(start=0.0, end=50.0)  # t=8 → 25
        layer_b = make_event(start=30.0, end=70.0)  # t=8 → 50
        line = make_rot_line([[layer_a], [layer_b], [], []])
        assert judge_line_rotate_at(line, 8.0) == pytest.approx(75.0)

    def test_no_events_returns_zero(self):
        line = make_rot_line([[], [], [], []])
        assert judge_line_rotate_at(line, 3.0) == 0.0

    def test_holds_last_event_end_value(self):
        ev = make_event(start=0.0, end=-180.0)
        line = make_rot_line([[ev], [], [], []])
        assert judge_line_rotate_at(line, 40.0) == pytest.approx(-180.0)

    def test_zero_duration_holds_end_value(self):
        # 零时长事件：t >= endTime 恒成立 → 走"结束保持"分支，不插值
        ev = make_event(start=10.0, end=50.0, start_time=(4, 0, 1), end_time=(4, 0, 1))
        line = make_rot_line([[ev], [], [], []])
        assert judge_line_rotate_at(line, 4.0) == pytest.approx(50.0)

    def test_before_first_event_returns_zero(self):
        ev = make_event(start=45.0, end=45.0, start_time=(4, 0, 1), end_time=(8, 0, 1))
        line = make_rot_line([[ev], [], [], []])
        assert judge_line_rotate_at(line, 2.0) == 0.0


class TestJudgeLineXHoldValue:
    """事件结束后判定线保持结束值，不回落 0（与 Phigros 一致）。"""

    def test_holds_last_event_end_value(self):
        # 事件 [0,16] 值 0→450；t=40 无后续事件 → 保持 450（用户报告的场景）
        ev = make_event(start=0.0, end=450.0)
        line = make_line([[ev], [], [], []])
        assert judge_line_x_at(line, 40.0) == pytest.approx(450.0)

    def test_gap_between_events_holds_previous_end(self):
        # 事件间空隙：e1 已结束（保持 100），e2 未开始
        e1 = make_event(start=0.0, end=100.0, start_time=(0, 0, 1), end_time=(8, 0, 1))
        e2 = make_event(start=100.0, end=200.0, start_time=(16, 0, 1), end_time=(24, 0, 1))
        line = make_line([[e1, e2], [], [], []])
        assert judge_line_x_at(line, 12.0) == pytest.approx(100.0)

    def test_multi_layer_hold_value_summed(self):
        layer_a = make_event(start=0.0, end=450.0)  # 默认 [0,16]，t=40 保持 450
        layer_b = make_event(start=0.0, end=-50.0, start_time=(0, 0, 1), end_time=(8, 0, 1))
        line = make_line([[layer_a], [layer_b], [], []])
        assert judge_line_x_at(line, 40.0) == pytest.approx(400.0)

    def test_before_first_event_returns_zero(self):
        ev = make_event(start_time=(4, 0, 1), end_time=(8, 0, 1))
        line = make_line([[ev], [], [], []])
        assert judge_line_x_at(line, 2.0) == 0.0

    def test_endpoint_equals_end_value(self):
        # t 恰在 endTime：插值分支与保持分支结果一致
        ev = make_event(start=0.0, end=100.0, start_time=(0, 0, 1), end_time=(8, 0, 1))
        line = make_line([[ev], [], [], []])
        assert judge_line_x_at(line, 8.0) == pytest.approx(100.0)
