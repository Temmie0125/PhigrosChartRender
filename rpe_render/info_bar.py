"""底部信息栏渲染：谱面元信息与 Note 统计数据。"""

from __future__ import annotations

import logging

import matplotlib
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .constants import INFO_BAR_BG_COLOR, INFO_BAR_TEXT_COLOR
from .models import ChartData, NoteCountStats, NoteData
from .time_utils import timet_to_beats

logger = logging.getLogger("rpe_render")

META_FONT_SIZE = 22
STATS_FONT_SIZE = 26

# 常见中文字体回退链（Windows / macOS / Linux）
_CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
)

_font_configured = False


def configure_cjk_font() -> None:
    """配置 matplotlib 使用可用的中文字体（幂等）。"""
    global _font_configured
    if _font_configured:
        return

    try:
        from matplotlib import font_manager

        available = {f.name for f in font_manager.fontManager.ttflist}
        for name in _CJK_FONT_CANDIDATES:
            if name in available:
                matplotlib.rcParams["font.sans-serif"] = [name]
                logger.debug("Using CJK font: %s", name)
                break
        else:
            logger.warning(
                "No CJK font found among %s; Chinese labels may show as boxes",
                ", ".join(_CJK_FONT_CANDIDATES),
            )
    except Exception:  # noqa: BLE001 - 字体探测失败不应阻断渲染
        logger.exception("CJK font detection failed")

    # 负号在非 DejaVu 字体下的显示修正
    matplotlib.rcParams["axes.unicode_minus"] = False
    _font_configured = True


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


def render_info_bar(
    fig: Figure,
    ax: Axes,
    chart: ChartData,
    note_counts: NoteCountStats,
    total_duration_seconds: float,
    canvas_width_px: float,
    canvas_height_px: float,
) -> None:
    """在画布底部绘制信息栏。

    布局:
    ┌──────────────────────────────────────────────────────────┐
    │ 左侧（谱面元信息）              │ 右侧（Note 统计）        │
    │ 谱面名称: xxx                   │ Tap: N    Drag: N        │
    │ 时长: m:ss | 难度: xxx          │ Flick: N  Hold: N        │
    │     曲师: xxx | 谱师: xxx           │                          │
    │ 基准BPM: xxx                    │                          │
    └──────────────────────────────────────────────────────────┘
    """
    del canvas_width_px, canvas_height_px  # 信息栏 Axes 已由调用方定位

    configure_cjk_font()

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_facecolor(INFO_BAR_BG_COLOR)

    meta = chart.meta
    base_bpm = chart.bpm_list[0].bpm if chart.bpm_list else 0.0

    left_x = 0.02
    right_x = 0.98
    line_ys = (0.78, 0.56, 0.34, 0.12)

    lines_left = [
        f"谱面名称: {meta.name}",
        f"时长: {format_duration(total_duration_seconds)}  |  难度: {meta.level}",
        f"曲师: {meta.composer}  |  谱师: {meta.charter}",
        f"基准BPM: {base_bpm:g}",
    ]

    for y, text in zip(line_ys, lines_left):
        ax.text(
            left_x,
            y,
            text,
            ha="left",
            va="center",
            fontsize=META_FONT_SIZE,
            color=INFO_BAR_TEXT_COLOR,
            transform=ax.transAxes,
        )

    lines_right = [
        f"Tap: {note_counts.tap}    Drag: {note_counts.drag}",
        f"Flick: {note_counts.flick}    Hold: {note_counts.hold}",
        f"Total: {note_counts.total}",
    ]

    for y, text in zip(line_ys[:3], lines_right):
        ax.text(
            right_x,
            y,
            text,
            ha="right",
            va="center",
            fontsize=STATS_FONT_SIZE,
            color=INFO_BAR_TEXT_COLOR,
            transform=ax.transAxes,
        )

    # 顶部细分隔线
    ax.axhline(y=0.995, color=INFO_BAR_TEXT_COLOR, alpha=0.25, linewidth=1.0)
