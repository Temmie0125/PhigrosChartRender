"""网格线与拍号标记：在 matplotlib Axes 上绘制时间轴网格系统。"""

from __future__ import annotations

from matplotlib.axes import Axes

from .constants import (
    BAR_LINE_ALPHA,
    BAR_LINE_COLOR,
    BAR_LINE_INTERVAL,
    BAR_LINE_WIDTH,
    BEAT_HEIGHT_PX,
    BEAT_LINE_ALPHA,
    BEAT_LINE_COLOR,
    BEAT_LINE_WIDTH,
    BEAT_MARK_FONT_SIZE,
    BEAT_MARK_INTERVAL,
    BPM_MARK_FONT_SIZE,
    BPM_MARK_INSET_PX,
    BPM_TEXT_COLOR,
    MARKER_MARGIN_PX,
    MARKER_TEXT_COLOR,
)
from .fonts import get_font
from .models import BPMEvent, ColumnInfo
from .time_utils import timet_to_beats

# Z 轴顺序：网格线在最低层，标记文字在 Note 之上
GRID_ZORDER = 0
MARKER_ZORDER = 20


def _edge_va(y: float, col: ColumnInfo) -> str:
    """标记文字的垂直对齐：避开画布上下边缘（信息栏交界处）裁剪。

    底部（y<=0）文字向上生长（va=bottom），顶部（y>=上边界）文字
    向下生长（va=top），其余居中，保证文字完整可见。
    """
    if y <= 0:
        return "bottom"
    if y >= col.pixel_top:
        return "top"
    return "center"


def render_grid(ax: Axes, columns: list[ColumnInfo], bpm_list: list[BPMEvent]) -> None:
    """在 Axes 上绘制完整的网格系统（所有分栏）。

    绘制内容：
        1. 拍线（每拍）与小节线（每 4 拍）
        2. 栏左侧的拍号标记（每 4 拍）
        3. 左侧 BPM 变化标记
    """
    for i, col in enumerate(columns):
        render_single_column_grid(
            ax, col, bpm_list, is_first_column=(i == 0)
        )


def render_single_column_grid(
    ax: Axes,
    col: ColumnInfo,
    bpm_list: list[BPMEvent],
    is_first_column: bool = True,
) -> None:
    """渲染单个分栏的网格线与左侧标记。"""
    beat_start = int(col.beat_start)
    beat_end = int(col.beat_end)

    # ---- 拍线 / 小节线 ----
    for beat in range(beat_start, beat_end + 1):
        y = (beat - col.beat_start) * BEAT_HEIGHT_PX + col.pixel_bottom
        x_left = col.pixel_left
        x_right = col.pixel_right

        if beat % BAR_LINE_INTERVAL == 0:
            ax.plot(
                [x_left, x_right],
                [y, y],
                color=BAR_LINE_COLOR,
                alpha=BAR_LINE_ALPHA,
                linewidth=BAR_LINE_WIDTH,
                zorder=GRID_ZORDER,
                solid_capstyle="butt",
            )
        else:
            ax.plot(
                [x_left, x_right],
                [y, y],
                color=BEAT_LINE_COLOR,
                alpha=BEAT_LINE_ALPHA,
                linewidth=BEAT_LINE_WIDTH,
                zorder=GRID_ZORDER,
                solid_capstyle="butt",
            )

    # ---- 拍号标记（每 4 拍，统一绘制在栏左侧）----
    for beat in range(beat_start, beat_end + 1, BEAT_MARK_INTERVAL):
        y = (beat - col.beat_start) * BEAT_HEIGHT_PX + col.pixel_bottom
        ax.text(
            col.pixel_left - MARKER_MARGIN_PX,
            y,
            str(beat),
            ha="right",
            va=_edge_va(y, col),
            fontproperties=get_font(BEAT_MARK_FONT_SIZE),
            color=MARKER_TEXT_COLOR,
            zorder=MARKER_ZORDER,
        )

    # ---- BPM 标记（栏内最左侧，避免与栏外左缘的拍号标记重合）----
    for bpm_event in bpm_list:
        bpm_beat = timet_to_beats(tuple(bpm_event.start_time))
        if col.beat_start <= bpm_beat < col.beat_end:
            y = (bpm_beat - col.beat_start) * BEAT_HEIGHT_PX + col.pixel_bottom
            # 默认显示在拍线上方 14px；底部边缘放不下时折到拍线下方
            y_anchor = y + 18.0 if y - 14.0 < 0.0 else y - 14.0
            ax.text(
                col.pixel_left + BPM_MARK_INSET_PX,
                y_anchor,
                f"BPM:{bpm_event.bpm:g}",
                ha="left",
                va="top",
                fontproperties=get_font(BPM_MARK_FONT_SIZE),
                color=BPM_TEXT_COLOR,
                zorder=MARKER_ZORDER,
            )
