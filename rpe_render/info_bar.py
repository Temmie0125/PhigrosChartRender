"""底部信息栏渲染：谱面元信息与 Note 统计数据。"""

from __future__ import annotations

import logging

from matplotlib.axes import Axes
from matplotlib.patches import FancyBboxPatch, Rectangle

from .constants import (
    INFO_BAR_BORDER_COLOR,
    INFO_BAR_BORDER_GAP_PX,
    INFO_BAR_BORDER_WIDTH_PX,
    INFO_BAR_HEIGHT_PX,
    INFO_BAR_OUTER_BORDER_ALPHA,
    INFO_BAR_ROUNDING_PX,
    INFO_BAR_TEXT_COLOR,
    INFO_BAR_TITLE_COLOR,
    NOTE_COLOR_DRAG,
    NOTE_COLOR_FLICK,
    NOTE_COLOR_HOLD,
    NOTE_COLOR_TAP,
    PREVIEW_BG_ALPHA,
    SIDE_MARKER_PADDING_PX,
)
from .fonts import configure_cjk_font, get_font
from .models import ChartData, NoteCountStats, NoteData
from .time_utils import timet_to_beats

logger = logging.getLogger("rpe_render")

TITLE_FONT_SIZE = 21
CONTENT_FONT_SIZE = 19

# 信息栏文字布局（px，数据坐标单位 = px）
# 文字与内层圆角边框之间四周保留统一间距（上下 = 左右 ≈ 29px），
# 与 INFO_BAR_HEIGHT_PX 配套：320px 高时标题 + 5 行统计可居中留出该边距
_ROW_PITCH_PX = 40.0  # 标题下方各行间隔
_TITLE_Y_PX = 260.0  # 标题中心 Y
_MARGIN_X_PX = 42.0  # 文字距信息栏左右边缘（内框内缘约 29px）


def compute_note_stats(notes: list[NoteData]) -> NoteCountStats:
    """统计各类型 Note 数量。"""
    stats = NoteCountStats()
    for note in notes:
        if note.type == 1:
            stats.tap += 1
        elif note.type == 2:
            stats.hold += 1
        elif note.type == 3:
            stats.flick += 1
        elif note.type == 4:
            stats.drag += 1
    return stats


def beats_to_seconds(chart: ChartData, target_beat: float) -> float:
    """按 BPMList 将拍数积分换算为秒（支持 BPM 变化）。"""
    if not chart.bpm_list:
        return target_beat / 120.0 * 60.0

    events = sorted(chart.bpm_list, key=lambda e: timet_to_beats(tuple(e.start_time)))
    seconds = 0.0
    prev_beat = timet_to_beats(tuple(events[0].start_time))
    bpm = max(events[0].bpm, 1e-6)
    consumed_beat = prev_beat

    for event in events[1:]:
        event_beat = timet_to_beats(tuple(event.start_time))
        if event_beat >= target_beat:
            break
        segment = min(event_beat, target_beat) - consumed_beat
        seconds += segment * 60.0 / bpm
        consumed_beat = event_beat
        bpm = max(event.bpm, 1e-6)

    if target_beat > consumed_beat:
        seconds += (target_beat - consumed_beat) * 60.0 / bpm

    return seconds


def compute_duration_seconds(chart: ChartData) -> float:
    """计算谱面时长（秒）。

    若 META.duration 有效则优先使用；
    否则取所有 Note endTime 的最大拍数，按 BPM 时间轴换算为秒。
    """
    if chart.meta.duration and chart.meta.duration > 0:
        return float(chart.meta.duration)

    max_end_beat = 0.0
    for line in chart.judge_line_list:
        for note in line.notes:
            if note.end_time_beat > max_end_beat:
                max_end_beat = note.end_time_beat

    if max_end_beat <= 0 and chart.bpm_list:
        max_end_beat = timet_to_beats(tuple(chart.bpm_list[-1].start_time))

    return beats_to_seconds(chart, max_end_beat)


def format_duration(seconds: float) -> str:
    """将秒数格式化为 m:ss。"""
    total = int(round(seconds))
    minutes = total // 60
    secs = total % 60
    return f"{minutes}:{secs:02d}"


def compute_bpm_range(chart: ChartData) -> tuple[float, float]:
    """统计谱面 BPM 范围：BPMList 中的最低与最高 BPM。"""
    if not chart.bpm_list:
        return 0.0, 0.0
    values = [event.bpm for event in chart.bpm_list]
    return min(values), max(values)


def format_bpm_text(bpm_min: float, bpm_max: float) -> str:
    """格式化 BPM 显示：定速曲目只写单个精确值，变速曲目才写范围。"""
    if bpm_min == bpm_max:
        return f"BPM：{bpm_min:g}"
    return f"BPM：{bpm_min:g}~{bpm_max:g}"


def _draw_shadowed_title(
    ax: Axes,
    x: float,
    y: float,
    text: str,
    ha: str,
) -> None:
    """绘制带约 1px 阴影的标题（标题色 #4CC3F8 在上层）。

    阴影通过在标题下方 1px 处叠加半透明黑色副本实现。
    """
    ax.text(
        x,
        y - 1.0,
        text,
        ha=ha,
        va="center",
        fontproperties=get_font(TITLE_FONT_SIZE),
        color="#000000",
        alpha=0.5,
        zorder=4,
    )
    ax.text(
        x,
        y,
        text,
        ha=ha,
        va="center",
        fontproperties=get_font(TITLE_FONT_SIZE),
        color=INFO_BAR_TITLE_COLOR,
        zorder=5,
    )


def render_info_bar(
    ax: Axes,
    chart: ChartData,
    note_counts: NoteCountStats,
    total_duration_seconds: float,
    canvas_width_px: float,
) -> None:
    """在画布底部绘制信息栏（背景模糊曲绘由调用方铺好）。

    绘制顺序（自下而上）:
      1. 内部填充: 圆角矩形，与配置区（非轨道部分）相同的底色
         （黑色覆盖层 alpha=PREVIEW_BG_ALPHA 叠在模糊曲绘之上）
      2. 最外层边框: 透明度 0.75 的深灰色方框
      3. 内层圆角边框: 与外框间隔约 8px，3px 不透明深灰色
      4. 左侧 Basic Information（标题 #4CC3F8 + 1px 阴影），下方为白色
         基础信息（含 BPM 范围，如 BPM：120~180）；右侧 Notes Info，
         下方为按类型着色的 Note 统计（Tap/Drag/Hold/Flick），
         Combo 总数保持白色。

    坐标空间与主区一致采用像素坐标（数据单位 = px），便于按像素
    绘制边框、圆角与文字定位。

    布局:
    ┌──────────────────────────────────────────────────────────┐
    │ Basic Information          │ Notes Info                  │
    │ 谱面名称: xxx               │ Tap: N        (蓝)         │
    │ 时长: m:ss | 难度: xxx      │ Drag: N       (黄)         │
    │ 曲师: xxx | 谱师: xxx       │ Hold: N       (浅蓝)       │
    │ BPM：120~180               │ Flick: N      (红)         │
    │                            │ Combo: N      (白)         │
    └──────────────────────────────────────────────────────────┘

    Args:
        ax: 底部信息栏 Axes
        chart: 谱面数据
        note_counts: Note 统计
        total_duration_seconds: 谱面总时长（秒）
        canvas_width_px: 画布总宽（px，含两侧标记边距）
    """
    configure_cjk_font()

    # 与主区一致的像素坐标空间
    x_min = -SIDE_MARKER_PADDING_PX
    ax.set_xlim(x_min, x_min + canvas_width_px)
    ax.set_ylim(0, INFO_BAR_HEIGHT_PX)
    ax.axis("off")

    # ===== 双边框几何 =====
    # 外框描边中线内缩 1.5px：3px 描边恰好贴住信息栏边缘，不越界被裁切
    outer_inset = INFO_BAR_BORDER_WIDTH_PX / 2.0
    # 内框描边中线 = 外框描边中线 + 外框半宽 + 8px 间隔 + 内框半宽
    inner_inset = (
        outer_inset
        + INFO_BAR_BORDER_WIDTH_PX
        + INFO_BAR_BORDER_GAP_PX
        + INFO_BAR_BORDER_WIDTH_PX / 2.0
    )
    inner_w = canvas_width_px - 2 * inner_inset
    inner_h = INFO_BAR_HEIGHT_PX - 2 * inner_inset
    boxstyle = f"round,pad=0,rounding_size={INFO_BAR_ROUNDING_PX}"

    # 内部填充: 与配置区（非轨道部分）相同的底色
    if PREVIEW_BG_ALPHA > 0.0:
        ax.add_patch(
            FancyBboxPatch(
                (x_min + inner_inset, inner_inset),
                inner_w,
                inner_h,
                boxstyle=boxstyle,
                facecolor="black",
                alpha=PREVIEW_BG_ALPHA,
                edgecolor="none",
                zorder=1,
            )
        )

    # 最外层边框: 透明度 0.75 的深灰色方框
    ax.add_patch(
        Rectangle(
            (x_min + outer_inset, outer_inset),
            canvas_width_px - 2 * outer_inset,
            INFO_BAR_HEIGHT_PX - 2 * outer_inset,
            facecolor="none",
            edgecolor=INFO_BAR_BORDER_COLOR,
            linewidth=INFO_BAR_BORDER_WIDTH_PX,
            alpha=INFO_BAR_OUTER_BORDER_ALPHA,
            zorder=2,
        )
    )

    # 内层圆角边框: 3px 不透明深灰色
    ax.add_patch(
        FancyBboxPatch(
            (x_min + inner_inset, inner_inset),
            inner_w,
            inner_h,
            boxstyle=boxstyle,
            facecolor="none",
            edgecolor=INFO_BAR_BORDER_COLOR,
            linewidth=INFO_BAR_BORDER_WIDTH_PX,
            zorder=3,
        )
    )

    # ===== 左侧: Basic Information =====
    left_x = x_min + _MARGIN_X_PX
    meta = chart.meta
    bpm_min, bpm_max = compute_bpm_range(chart)
    _draw_shadowed_title(ax, left_x, _TITLE_Y_PX, "Basic Information", ha="left")

    lines_left = [
        f"谱面名称: {meta.name}",
        f"时长: {format_duration(total_duration_seconds)}  |  难度: {meta.level}",
        f"曲师: {meta.composer}  |  谱师: {meta.charter}",
        format_bpm_text(bpm_min, bpm_max),
    ]
    for idx, text in enumerate(lines_left):
        ax.text(
            left_x,
            _TITLE_Y_PX - (idx + 1) * _ROW_PITCH_PX,
            text,
            ha="left",
            va="center",
            fontproperties=get_font(CONTENT_FONT_SIZE),
            color=INFO_BAR_TEXT_COLOR,
            zorder=5,
        )

    # ===== 右侧: Notes Info（统计文本按 Note 类型着色） =====
    right_x = x_min + canvas_width_px - _MARGIN_X_PX
    _draw_shadowed_title(ax, right_x, _TITLE_Y_PX, "Notes Info", ha="right")

    lines_right = [
        (f"Tap: {note_counts.tap}", NOTE_COLOR_TAP),
        (f"Drag: {note_counts.drag}", NOTE_COLOR_DRAG),
        (f"Hold: {note_counts.hold}", NOTE_COLOR_HOLD),
        (f"Flick: {note_counts.flick}", NOTE_COLOR_FLICK),
        (f"Combo: {note_counts.total}", INFO_BAR_TEXT_COLOR),
    ]
    for idx, (text, color) in enumerate(lines_right):
        ax.text(
            right_x,
            _TITLE_Y_PX - (idx + 1) * _ROW_PITCH_PX,
            text,
            ha="right",
            va="center",
            fontproperties=get_font(CONTENT_FONT_SIZE),
            color=color,
            zorder=5,
        )
