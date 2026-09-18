"""事件值求值器：含多层级叠加、缓动截取与贝塞尔缓动。"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import cos, radians, sin
from typing import TYPE_CHECKING, Optional

from ..models import ChartData, EventData, EventLayer, JudgeLineData
from .bezier import BezierEasing
from .functions import EASING_TYPE_TO_NAME, get_easing_by_type

if TYPE_CHECKING:  # pragma: no cover
    pass

# 事件生效瞬间的判定容差（拍）：吸收 judge_line_pose_at 中 bpmfactor 往返
# 换算引入的浮点误差。该值远小于任何有意义的拍数差（174 BPM 下 1e-9 拍
# 约 3e-10 秒）。
EVENT_START_EPSILON = 1e-9


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
    t_start = event.start_beat
    t_end = event.end_beat
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
        t_start = event.start_beat
        t_end = event.end_beat
        if t_start <= t_beat <= t_end:
            return event
    return None


def _latest_started_event(
    layer: EventLayer,
    attr_name: str,
    t_beat: float,
    before_start: bool = False,
) -> EventData | None:
    """查找该层级在时刻 t_beat 生效的事件。

    before_start=False: 取最后一个 startTime <= t_beat 的事件（覆盖中或
        已结束保持）。
    before_start=True: 取「生效前」的事件，即最后一个
        startTime < t_beat - EVENT_START_EPSILON 的事件；容差同时吸收
        浮点误差与同 startTime 的重复事件。

    事件列表在 chart_parser 解析时已按 startTime 排序；此处覆盖式选取
    对乱序输入同样稳健（索引按事件列表对象惰性缓存）。
    """
    events = getattr(layer, attr_name)
    cached = layer.event_indices.get(attr_name)
    if cached is None or cached[0] is not events:
        ordered = sorted(events, key=lambda event: event.start_beat)
        starts = [event.start_beat for event in ordered]
        cached = (events, ordered, starts)
        layer.event_indices[attr_name] = cached
    else:
        _, ordered, starts = cached
    if before_start:
        index = bisect_left(starts, t_beat - EVENT_START_EPSILON) - 1
    else:
        index = bisect_right(starts, t_beat) - 1
    return ordered[index] if index >= 0 else None


def _value_before_event(
    layer: EventLayer, attr_name: str, t_beat: float, active: EventData
) -> float | None:
    """事件 active 在 t_beat 生效前的属性值（该层级的贡献）。

    返回 None 表示 active 是判定线该层级的首个事件且自时间轴起点
    （startTime <= 0）开始，此前没有任何已渲染画面，调用方应改用事件
    自身在该时刻的值。
    """
    previous = _latest_started_event(layer, attr_name, t_beat, before_start=True)
    if previous is None:
        # 无更早事件：生效前即判定线默认值 0（起点例外见 docstring）
        return None if active.start_beat <= 0.0 else 0.0
    if t_beat >= previous.end_beat:
        return previous.end
    return evaluate_event_value(previous, t_beat)


def _judge_line_attr_at(line: JudgeLineData, t_beat: float, attr_name: str) -> float:
    """计算判定线某类属性事件在时刻 t_beat 的叠加值（通用实现）。

    ★ 关键设计: 遍历全部 4 个 eventLayers，对每个层级独立查找该时刻
    生效的事件（moveX / rotate 等），将找到的值直接叠加（求和）。

    事件持续语义（与 Phigros 一致）：
    - t 处于事件区间 [start, end) 内 → 按缓动插值
    - t >= 事件 endTime 且无更晚事件 → 保持该事件的结束值（event.end），
      不会回落到 0（若无此保持，事件间隙中的 Note 会被误判为默认值）
    - 谱面开始到第一个事件之前 → 0.0（默认位置）
    - t 恰为某事件的生效瞬间 → 取该事件生效前的值（见下）

    生效瞬间语义（跳变）：
    事件在 startTime 处可能相对生效前的值发生瞬间跳变（如从 0 跳到
    300），而游戏内该瞬间看到的仍是生效前的画面。因此当 t_beat 恰为
    某事件的 startTime（判定容差 EVENT_START_EPSILON）时，按生效前的
    值渲染：取更早的事件（结束则保持其结束值，否则在 t 处插值），若该
    事件是判定线首个事件且自时间轴起点开始（startTime <= 0）则属起点
    例外——此前没有已渲染画面，仍按事件自身取值。

    跳变判据与缓动类型无关（Out / In / InOut / linear 一视同仁），因为
    无跳变时生效前值与事件起始值本就相同，规则等价于空操作。零时长事件
    （start == end）恒命中结束保持分支，保持「即时生效」语义。

    Args:
        line: 判定线数据
        t_beat: 目标时刻（拍数）
        attr_name: 事件属性名（如 "move_x_events" / "rotate_events"）

    Returns:
        所有层级叠加后的属性值。
    """
    total = 0.0
    for layer in line.event_layers:
        events = getattr(layer, attr_name)
        active = _latest_started_event(layer, attr_name, t_beat) if events else None
        if active is None:
            continue
        if t_beat >= active.end_beat:
            total += active.end  # 事件结束后的保持值（零时长事件亦走此分支）
        elif abs(active.start_beat - t_beat) <= EVENT_START_EPSILON:
            # 生效瞬间：取生效前的值；None 表示起点例外，按事件自身取值
            value = _value_before_event(layer, attr_name, t_beat, active)
            total += evaluate_event_value(active, t_beat) if value is None else value
        else:
            total += evaluate_event_value(active, t_beat)
    return total


def judge_line_x_at(line: JudgeLineData, t_beat: float) -> float:
    """计算判定线在时刻 t_beat 的 X 坐标（4 层 moveXEvents 叠加）。"""
    return _judge_line_attr_at(line, t_beat, "move_x_events")


def judge_line_y_at(line: JudgeLineData, t_beat: float) -> float:
    """计算判定线在时刻 t_beat 的局部 Y 坐标。"""
    return _judge_line_attr_at(line, t_beat, "move_y_events")


def judge_line_rotate_at(line: JudgeLineData, t_beat: float) -> float:
    """计算判定线在时刻 t_beat 的角度（4 层 rotateEvents 叠加）。

    语义与 judge_line_x_at 一致（覆盖式选取 + 结束保持），无事件返回 0.0。
    单位: 度。
    """
    return _judge_line_attr_at(line, t_beat, "rotate_events")


@dataclass(frozen=True)
class JudgeLinePose:
    """判定线在统一游戏坐标系中的位置和方向。"""

    x: float
    y: float
    angle: float


def judge_line_pose_at(
    chart: ChartData,
    line_index: int,
    local_beat: float,
    _stack: tuple[int, ...] = (),
) -> JudgeLinePose:
    """递归计算判定线在世界坐标系中的姿态。

    子线的局部 moveX/moveY 位于父线坐标系中；父线旋转始终影响该坐标
    变换，而 ``rotate_with_father`` 仅控制父线角度是否叠加到子线自身角度。
    ``_stack`` 仅用于防御性检测，正常输入已在 chart_parser 校验过。
    """
    if line_index < 0 or line_index >= len(chart.judge_line_list):
        raise ValueError(f"invalid judge line index: {line_index}")
    if line_index in _stack:
        raise ValueError(f"judge line father cycle detected at index {line_index}")

    line = chart.judge_line_list[line_index]
    local_x = judge_line_x_at(line, local_beat)
    local_y = judge_line_y_at(line, local_beat)
    local_angle = judge_line_rotate_at(line, local_beat)

    if line.father == -1:
        return JudgeLinePose(local_x, local_y, local_angle)

    # 父子线可能拥有不同 bpmfactor；父线姿态必须取与当前子线时刻相同
    # 的主谱面实际时间，而不能直接复用子线的本地拍数。
    display_beat = local_beat * line.bpm_factor
    parent_line = chart.judge_line_list[line.father]
    parent_local_beat = display_beat / parent_line.bpm_factor
    parent = judge_line_pose_at(
        chart, line.father, parent_local_beat, _stack + (line_index,)
    )
    theta = radians(parent.angle)
    world_x = parent.x + local_x * cos(theta) - local_y * sin(theta)
    world_y = parent.y + local_x * sin(theta) + local_y * cos(theta)
    world_angle = local_angle + (parent.angle if line.rotate_with_father else 0.0)
    return JudgeLinePose(world_x, world_y, world_angle)


def judge_line_world_x_at(
    chart: ChartData, line_index: int, local_beat: float
) -> float:
    """计算判定线世界坐标 X。"""
    return judge_line_pose_at(chart, line_index, local_beat).x


def judge_line_world_angle_at(
    chart: ChartData, line_index: int, local_beat: float
) -> float:
    """计算判定线世界坐标角度。"""
    return judge_line_pose_at(chart, line_index, local_beat).angle


__all__ = [
    "EASING_TYPE_TO_NAME",
    "compute_eased_progress",
    "evaluate_event_value",
    "find_enclosing_event",
    "JudgeLinePose",
    "judge_line_pose_at",
    "judge_line_world_angle_at",
    "judge_line_world_x_at",
    "judge_line_rotate_at",
    "judge_line_x_at",
    "judge_line_y_at",
]
