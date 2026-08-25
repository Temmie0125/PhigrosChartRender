"""事件值求值器：含多层级叠加、缓动截取与贝塞尔缓动。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ..models import EventData, JudgeLineData
from ..time_utils import timet_to_beats
from .bezier import BezierEasing
from .functions import EASING_TYPE_TO_NAME, get_easing_by_type

if TYPE_CHECKING:  # pragma: no cover
    pass


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def compute_eased_progress(
    progress: float,
    easing_type: int,
    easing_left: float,
    easing_right: float,
    bezier: bool,
    bezier_points: list[float],
) -> float:
    """计算经缓动映射后的进度值。

    缓动截取公式（来自需求文档）:
        g(t) = [f(r) - f(l)] * f((t - l) / (r - l)) + f(l)

    其中 f 为原始缓动函数，l=easingLeft, r=easingRight。

    Raises:
        KeyError: 未知 easing_type
        ValueError: easing_left == easing_right 时无法截取
    """
    # 1. 获取原始缓动函数
    f = get_easing_by_type(easing_type)

    # 2. 若使用贝塞尔缓动：用 BezierEasing 的查找函数替代 f
    if bezier and bezier_points is not None and len(bezier_points) >= 4:
        cp1 = (float(bezier_points[0]), float(bezier_points[1]))
        cp2 = (float(bezier_points[2]), float(bezier_points[3]))
        curve = BezierEasing(cp1, cp2)
        f = curve.get_value

    left = float(easing_left)
    right = float(easing_right)

    # 3. 应用缓动截取
    if left != 0.0 or right != 1.0:
        fl = f(left)
        fr = f(right)
        span = right - left
        if span == 0.0:
            raise ValueError("easing_left must not equal easing_right")
        scaled_t = (progress - left) / span
        eased = (fr - fl) * f(scaled_t) + fl
    else:
        eased = f(progress)

    # 4. clamp 到 [0, 1]
    return _clamp01(eased)


def evaluate_event_value(event: EventData, t_beat: float) -> float:
    """计算单个事件在时刻 t_beat（拍数）的属性值。

    Raises:
        ValueError: 若事件时长为零（t_end == t_start）
        KeyError: 若 easing_type 未知
    """
    t_start = timet_to_beats(event.start_time)
    t_end = timet_to_beats(event.end_time)
    duration = t_end - t_start
    if duration == 0.0:
        raise ValueError("event has zero duration (startTime == endTime)")

    progress = (t_beat - t_start) / duration

    eased = compute_eased_progress(
        progress=progress,
        easing_type=event.easing_type,
        easing_left=event.easing_left,
        easing_right=event.easing_right,
        bezier=bool(event.bezier),
        bezier_points=event.bezier_points,
    )

    return event.start + (event.end - event.start) * eased


def find_enclosing_event(
    events: list[EventData],
    t_beat: float,
) -> Optional[EventData]:
    """在事件列表中查找覆盖 t_beat 时刻的事件。

    覆盖条件: startTime_beat <= t_beat <= endTime_beat

    Args:
        events: 事件列表（通常已按时间排序）
        t_beat: 目标时刻（拍数）

    Returns:
        覆盖该时刻的事件，若无则返回 None
    """
    for event in events:
        t_start = timet_to_beats(event.start_time)
        t_end = timet_to_beats(event.end_time)
        if t_start <= t_beat <= t_end:
            return event
    return None


def _judge_line_attr_at(line: JudgeLineData, t_beat: float, attr_name: str) -> float:
    """计算判定线某类属性事件在时刻 t_beat 的叠加值（通用实现）。

    ★ 关键设计: 遍历全部 4 个 eventLayers，对每个层级独立查找该时刻
    生效的事件（moveX / rotate 等），将找到的值直接叠加（求和）。

    事件持续语义（与 Phigros 一致）：
    - t 处于事件区间 [start, end) 内 → 按缓动插值
    - t >= 事件 endTime 且无更晚事件 → 保持该事件的结束值（event.end），
      不会回落到 0（若无此保持，事件间隙中的 Note 会被误判为默认值）
    - 谱面开始到第一个事件之前 → 0.0（默认位置）

    Args:
        line: 判定线数据
        t_beat: 目标时刻（拍数）
        attr_name: 事件属性名（如 "move_x_events" / "rotate_events"）

    Returns:
        所有层级叠加后的属性值。
    """
    total = 0.0
    for layer in line.event_layers:
        # 取最后一个 startTime <= t_beat 的事件（覆盖中或已结束保持）。
        # 事件列表在 chart_parser 解析时已按 startTime 排序；
        # 此处覆盖式选取对乱序输入同样稳健。
        active: Optional[EventData] = None
        for event in getattr(layer, attr_name):
            if timet_to_beats(event.start_time) <= t_beat:
                active = event
        if active is None:
            continue
        if t_beat >= timet_to_beats(active.end_time):
            total += active.end  # 事件结束后的保持值
        else:
            total += evaluate_event_value(active, t_beat)
    return total


def judge_line_x_at(line: JudgeLineData, t_beat: float) -> float:
    """计算判定线在时刻 t_beat 的 X 坐标（4 层 moveXEvents 叠加）。"""
    return _judge_line_attr_at(line, t_beat, "move_x_events")


def judge_line_rotate_at(line: JudgeLineData, t_beat: float) -> float:
    """计算判定线在时刻 t_beat 的角度（4 层 rotateEvents 叠加）。

    语义与 judge_line_x_at 一致（覆盖式选取 + 结束保持），无事件返回 0.0。
    单位: 度。
    """
    return _judge_line_attr_at(line, t_beat, "rotate_events")


__all__ = [
    "EASING_TYPE_TO_NAME",
    "compute_eased_progress",
    "evaluate_event_value",
    "find_enclosing_event",
    "judge_line_rotate_at",
    "judge_line_x_at",
]
