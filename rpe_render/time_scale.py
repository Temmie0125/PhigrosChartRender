"""BPM 缩放倍率：将谱面全部时间数值与 BPM 值按统一倍率缩放。

部分谱面以 N 倍 BPM 书写（如实际 180 BPM 按 540 书写，以获得更细的
时间粒度），渲染画布会按相同倍数增大。对这类谱面指定 1/N 的缩放倍率，
即可把时值与 BPM 数值整体还原到真实节奏，画布尺寸随之恢复正常。

缩放语义:
    - 音符时值、事件时间、BPMList 时间统一乘以 factor；
    - BPM 数值（BPMList 与官谱各判定线）同步乘以 factor，因此真实秒时长
      （拍数×f ÷ BPM×f）保持不变，信息栏时长文本无需修正；
    - bpm_factor 是比值（缩放不变量）、坐标与事件值等空间数值、
      META.duration（秒）均不缩放。
"""

from __future__ import annotations

from fractions import Fraction
from math import isclose

from .models import ChartData, EventData
from .time_utils import timet_to_beats

# 允许的缩放档位（与 Web UI 下拉框一致）。
ALLOWED_BPM_SCALES: tuple[float, ...] = (0.25, 1.0 / 3.0, 0.5, 1.0, 2.0, 3.0, 4.0)

_ALLOWED_SCALE_TEXT = "1/4、1/3、1/2、1、2、3、4"

# 浮点倍率与档位匹配的绝对容差（1/3 等分数经二进制浮点折损后仍可命中）。
_SCALE_MATCH_TOLERANCE = 1e-9


def normalize_bpm_scale(value: float | str) -> float:
    """校验并归一 BPM 缩放倍率，仅允许 ALLOWED_BPM_SCALES 中的档位。

    支持 "1/3" 分数写法与浮点写法；1/3 等以近似浮点传入时按容差命中档位，
    返回档位本身的精确值。

    Raises:
        ValueError: 数值无法解析或不属于允许的档位。
    """
    if isinstance(value, str):
        text = value.strip()
        if "/" in text:
            numerator, _, denominator = text.partition("/")
            try:
                scale = int(numerator) / int(denominator)
            except (ValueError, ZeroDivisionError) as exc:
                raise ValueError(
                    f"bpm_scale 无法解析: {value!r}；支持 {_ALLOWED_SCALE_TEXT}"
                ) from exc
        else:
            try:
                scale = float(text)
            except ValueError as exc:
                raise ValueError(
                    f"bpm_scale 无法解析: {value!r}；支持 {_ALLOWED_SCALE_TEXT}"
                ) from exc
    else:
        try:
            scale = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"bpm_scale 无法解析: {value!r}；支持 {_ALLOWED_SCALE_TEXT}"
            ) from exc
    for allowed in ALLOWED_BPM_SCALES:
        if isclose(scale, allowed, rel_tol=0.0, abs_tol=_SCALE_MATCH_TOLERANCE):
            return allowed
    raise ValueError(f"bpm_scale 必须是 {_ALLOWED_SCALE_TEXT} 之一，got {scale:g}")


def scale_chart_time(chart: ChartData, factor: float) -> None:
    """按倍率原地缩放谱面全部时间数值与 BPM 值。

    factor 为 1 时不做任何修改；factor 必须为正数。
    """
    if factor == 1.0:
        return
    if factor <= 0:
        raise ValueError(f"bpm_scale must be positive, got {factor}")
    # 常用档位均为小整数比，用分数精确缩放 TimeT，避免累积浮点误差。
    ratio = Fraction(factor).limit_denominator(1_000_000)
    for event in chart.bpm_list:
        event.start_time = _scale_timet(event.start_time, ratio)
        event.bpm *= factor
    for line in chart.judge_line_list:
        if line.bpm > 0:
            line.bpm *= factor
        for note in line.notes:
            note.start_time_beat *= factor
            note.end_time_beat *= factor
            if len(note.raw_start_time) == 3:
                note.raw_start_time = _scale_timet(note.raw_start_time, ratio)
            if len(note.raw_end_time) == 3:
                note.raw_end_time = _scale_timet(note.raw_end_time, ratio)
        for layer in line.event_layers:
            for events in (
                layer.move_x_events,
                layer.move_y_events,
                layer.rotate_events,
                layer.alpha_events,
                layer.speed_events,
            ):
                for event in events:
                    _scale_event_time(event, ratio)


def _scale_event_time(event: EventData, ratio: Fraction) -> None:
    """缩放单个事件的时间，并按解析路径从 TimeT 重算拍数缓存。"""
    event.start_time = _scale_timet(event.start_time, ratio)
    event.end_time = _scale_timet(event.end_time, ratio)
    event.start_beat = timet_to_beats(tuple(event.start_time))
    event.end_beat = timet_to_beats(tuple(event.end_time))


def _scale_timet(tt: list[int], ratio: Fraction) -> list[int]:
    """将 TimeT [integer, numerator, denominator] 按分数比精确缩放。

    结构异常（长度不为 3、分母为 0、非整数分量）时原样返回，交由既有
    校验路径报告问题。
    """
    if len(tt) != 3:
        return list(tt)
    try:
        integer, numerator, denominator = int(tt[0]), int(tt[1]), int(tt[2])
    except (TypeError, ValueError):
        return list(tt)
    if denominator == 0:
        return list(tt)
    scaled = Fraction(integer * denominator + numerator, denominator) * ratio
    total, den = scaled.numerator, scaled.denominator
    return [total // den, total % den, den]


__all__ = ["ALLOWED_BPM_SCALES", "normalize_bpm_scale", "scale_chart_time"]
