"""时间轴计算与分栏：拍数/游戏坐标 → 像素坐标的纯计算模块。

不涉及任何 matplotlib 渲染。
"""

from __future__ import annotations

import logging
from math import ceil

from .constants import (
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    COLUMN_GAP,
    COLUMN_WIDTH,
    GAME_X_MAX,
    GAME_X_MIN,
    INFO_BAR_HEIGHT_PX,
    OUTPUT_DPI,
    SIDE_MARKER_PADDING_PX,
)
from .models import ChartData, ColumnInfo, JudgeLineData, NoteData

logger = logging.getLogger("rpe_render")


def compute_columns(max_beat: float) -> list[ColumnInfo]:
    """根据谱面总拍数计算所有分栏信息。

    分栏规则:
    - 每栏 COLUMN_BEATS（64）拍
    - 栏宽 COLUMN_WIDTH（450px），栏间距 COLUMN_GAP（150px）
    - 单行从左到右排列（D11），不换行
    - 每栏 Y 坐标相同：底部 = 0，顶部 = 64 * 64 = 4096px

    Args:
        max_beat: 谱面最大拍数

    Returns:
        分栏信息列表（至少 1 栏）
    """
    if max_beat <= 0:
        num_columns = 1
    else:
        # max_beat 恰好落在栏边界时属于下一栏的开始，不需要额外一栏
        num_columns = int(ceil(max_beat / COLUMN_BEATS))
        if num_columns == 0:
            num_columns = 1

    columns: list[ColumnInfo] = []
    for index in range(num_columns):
        beat_start = index * COLUMN_BEATS
        beat_end = beat_start + COLUMN_BEATS
        pixel_left = index * (COLUMN_WIDTH + COLUMN_GAP)
        pixel_right = pixel_left + COLUMN_WIDTH
        columns.append(
            ColumnInfo(
                index=index,
                beat_start=float(beat_start),
                beat_end=float(beat_end),
                pixel_left=float(pixel_left),
                pixel_right=float(pixel_right),
                pixel_bottom=0.0,
                pixel_top=COLUMN_BEATS * BEAT_HEIGHT_PX,
            )
        )
    return columns


def beat_to_pixel(beat: float, columns: list[ColumnInfo]) -> tuple[int, float, float]:
    """将拍数映射到像素坐标。

    下落式: Y 从下往上递增，beat=0 在底部。

    Returns:
        (column_index, y_pixel, x_offset_for_column)

    Raises:
        ValueError: 若 beat 超出所有栏的范围
    """
    last = columns[-1]
    if beat < columns[0].beat_start or beat > last.beat_end + 1e-9:
        raise ValueError(
            f"Beat {beat} is out of range [{columns[0].beat_start}, {last.beat_end}]"
        )

    col_index = min(int(beat // COLUMN_BEATS), len(columns) - 1)
    y_in_column = (beat - col_index * COLUMN_BEATS) * BEAT_HEIGHT_PX
    x_offset = col_index * (COLUMN_WIDTH + COLUMN_GAP)
    return col_index, y_in_column, float(x_offset)


def x_to_pixel(note_x: float, column_left: float) -> float:
    """将游戏 X 坐标映射到像素 X 坐标。

    映射: note_x ∈ [GAME_X_MIN, GAME_X_MAX] → pixel ∈ [column_left, column_left + COLUMN_WIDTH]

    note_x 超出范围时 clamp 并记录警告。
    """
    span = GAME_X_MAX - GAME_X_MIN
    ratio = (note_x - GAME_X_MIN) / span

    clamped_ratio = ratio
    if ratio < 0.0:
        logger.warning("note_x %.2f below GAME_X_MIN, clamped", note_x)
        clamped_ratio = 0.0
    elif ratio > 1.0:
        logger.warning("note_x %.2f above GAME_X_MAX, clamped", note_x)
        clamped_ratio = 1.0

    return column_left + clamped_ratio * COLUMN_WIDTH


def compute_max_beat(chart: ChartData) -> float:
    """计算谱面的最大拍数。

    遍历所有判定线的所有 Note 取最大的 endTime 拍数；
    若无 Note，则取 BPMList 最后一个事件的 startTime。
    """
    max_beat = 0.0
    for line in chart.judge_line_list:
        for note in line.notes:
            if note.end_time_beat > max_beat:
                max_beat = note.end_time_beat

    if max_beat <= 0.0 and chart.bpm_list:
        max_beat = timet_to_beats_value(chart.bpm_list[-1].start_time)

    return max_beat


def timet_to_beats_value(tt: list[int]) -> float:
    """list[int] 版本的 TimeT 转换便捷函数。"""
    from .time_utils import timet_to_beats

    return timet_to_beats((tt[0], tt[1], tt[2]))


def merge_all_notes(chart: ChartData) -> list[tuple[NoteData, JudgeLineData]]:
    """收集所有判定线的全部 Note，合并为一个扁平列表。

    Returns:
        [(note, judge_line), ...]，保持与判定线的关联以便后续计算 X 坐标。
    """
    merged: list[tuple[NoteData, JudgeLineData]] = []
    for line in chart.judge_line_list:
        for note in line.notes:
            merged.append((note, line))
    return merged


def compute_canvas_size(columns: list[ColumnInfo]) -> tuple[float, float]:
    """计算最终画布尺寸（英寸）。

    宽度 = 最后栏右边界 + 两侧标记边距 / OUTPUT_DPI；
    高度 = (栏高 + 信息栏高) / OUTPUT_DPI。

    Returns:
        (width_inches, height_inches)
    """
    width_px = columns[-1].pixel_right + 2 * SIDE_MARKER_PADDING_PX
    height_px = COLUMN_BEATS * BEAT_HEIGHT_PX + INFO_BAR_HEIGHT_PX
    return width_px / OUTPUT_DPI, height_px / OUTPUT_DPI
