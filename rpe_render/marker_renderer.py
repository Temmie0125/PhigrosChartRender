"""时值标记、计数标记与位置重合标注。

时值间隔标记绘制在栏内侧右缘，累计计数标记绘制在栏外侧，二者互不重叠；
位置重合的 Note 组在其旁边标注 "×n"（栏内）。
"""

from __future__ import annotations

from math import ceil

from matplotlib.axes import Axes

from .constants import (
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    COUNT_MARK_INTERVAL,
    MARKER_MARGIN_PX,
    MARKER_TEXT_COLOR,
    MAX_INTERVAL_MARK_BEAT,
    NOTE_OVERLAP_LABEL_OFFSET_PX,
    NOTE_OVERLAP_THRESHOLD_X,
)
from .fonts import get_font
from .models import ColumnInfo, NoteRenderInfo

MARKER_ZORDER = 20

# 标记文字颜色统一取自 constants（默认白色，配合预览区黑色底色）
INTERVAL_TEXT_COLOR = MARKER_TEXT_COLOR
COUNT_TEXT_COLOR = MARKER_TEXT_COLOR

# 时值间隔标记向栏内收缩的距离（px）
INTERVAL_INSET_PX = 0.0


def compute_interval_markers(
    notes: list[NoteRenderInfo],
) -> list[tuple[float, float, str]]:
    """计算时值间隔标记。

    规则（D10）：
    - 筛选 type IN (Tap=1, Hold=2) 的 Note，跨类型混合后按 startTime 排序
    - 仅标记 0 < 间隔 <= MAX_INTERVAL_MARK_BEAT（1/4 拍，16 分音符）的位置；
      间隔大于 1/4 拍（如八分音符 1/2 拍）不标记
    - 标记文字为 N 分音符刻度：label = round(4 / interval)，
      如间隔 1/4 拍（16 分）→ "16"，1/8 拍（32 分）→ "32"
    - 标记位置取两个 Note 之间的间隔中点（而非第二个 Note 的位置），
      使标记落在间隔中央；栏索引按中点所属栏计算

    Returns:
        [(beat, column_index, label), ...]
    """
    filtered = [n for n in notes if n.note.type in (1, 2)]
    filtered.sort(key=lambda n: (n.beat, n.column))

    markers: list[tuple[float, float, str]] = []
    for i in range(1, len(filtered)):
        prev = filtered[i - 1]
        curr = filtered[i]
        interval = curr.beat - prev.beat  # 拍数差

        if 0 < interval <= MAX_INTERVAL_MARK_BEAT:
            label = str(round(4.0 / interval))
            mid_beat = (prev.beat + curr.beat) / 2.0  # 间隔中点
            markers.append(
                (mid_beat, float(int(mid_beat // COLUMN_BEATS)), label)
            )

    return markers


def compute_count_markers(
    notes: list[NoteRenderInfo],
    max_beat: float,
) -> list[tuple[float, float, int]]:
    """计算每 4 拍的 Note 累计计数标记。

    对每 4 拍的节点，统计从谱面开始到该时刻（含）的所有 Note 总数。

    Returns:
        [(beat, column_index, count), ...]
    """
    sorted_notes = sorted(notes, key=lambda n: n.beat)

    markers: list[tuple[float, float, int]] = []
    note_idx = 0
    cumulative = 0

    check_limit = ceil(max_beat)
    for check_beat in range(0, check_limit + 1, COUNT_MARK_INTERVAL):
        while note_idx < len(sorted_notes) and sorted_notes[note_idx].beat <= check_beat:
            cumulative += 1
            note_idx += 1
        col = int(check_beat // COLUMN_BEATS)
        markers.append((float(check_beat), float(col), cumulative))

    return markers


def compute_overlap_groups(
    notes: list[NoteRenderInfo],
    threshold_x: float = NOTE_OVERLAP_THRESHOLD_X,
) -> list[list[NoteRenderInfo]]:
    """按开始时间（startTime）聚类重合的 Note 组。

    规则（仅考虑开始时间处的重叠）：
    - 同一开始时间（beat 相同）的 Note 才可能重合；不同开始时间的
      Note 即使渲染位置接近也不成组
    - Hold 仅以头部（startTime）参与判定，持续期间覆盖的其他 Note 不计入
    - 组内进一步按谱面原始 X 距离聚类：与组内任一成员的 |true_x| 距离
      <= 阈值即视为重合

    Args:
        notes: 全部 Note 的渲染信息（需含 beat 与 true_x）
        threshold_x: 重合判定阈值（谱面原始 X 距离，游戏坐标单位，默认 75.0）

    Returns:
        重合组列表，每组 >= 2 个 Note；无重合时返回空列表
    """
    by_start: dict[float, list[NoteRenderInfo]] = {}
    for n in notes:
        by_start.setdefault(n.beat, []).append(n)

    groups: list[list[NoteRenderInfo]] = []
    for members in by_start.values():
        if len(members) < 2:
            continue
        # 同刻成员按原始 X 排序后贪心聚类（与组内任一成员距离 <= 阈值即入组）
        subs: list[list[NoteRenderInfo]] = []
        for member in sorted(members, key=lambda n: n.true_x):
            for sub in subs:
                if any(abs(member.true_x - m.true_x) <= threshold_x for m in sub):
                    sub.append(member)
                    break
            else:
                subs.append([member])
        groups.extend(sub for sub in subs if len(sub) >= 2)

    return groups


def _beat_to_y(beat: float, col_index: int) -> float:
    """栏内 Y 像素（下落式，从底部向上递增）。"""
    return (beat - col_index * COLUMN_BEATS) * BEAT_HEIGHT_PX


def _edge_va(y: float, col: ColumnInfo) -> str:
    """标记文字的垂直对齐：避开画布上下边缘（信息栏交界处）裁剪。"""
    if y <= 0:
        return "bottom"
    if y >= col.pixel_top:
        return "top"
    return "center"


def render_markers(
    ax: Axes,
    columns: list[ColumnInfo],
    notes: list[NoteRenderInfo],
) -> None:
    """在 Axes 上绘制所有标记（时值间隔 + 累计计数）。

    - 时值间隔标记：栏内侧右缘（向内靠），颜色 #666666，字号 7
    - 累计计数标记：栏外侧，颜色 #333333，字号 7
    """
    if not columns:
        return

    # ---- 时值间隔标记（栏内右缘，与外侧计数错开）----
    for beat, col_index, label in compute_interval_markers(notes):
        if col_index < 0 or col_index >= len(columns):
            continue
        col = columns[int(col_index)]
        y = _beat_to_y(beat, int(col_index))
        ax.text(
            col.pixel_right - INTERVAL_INSET_PX,
            y,
            label,
            ha="right",
            va=_edge_va(y, col),
            fontproperties=get_font(7.0),
            color=INTERVAL_TEXT_COLOR,
            zorder=MARKER_ZORDER,
        )

    # ---- 累计计数标记（栏外右侧）----
    max_beat = columns[-1].beat_end
    for beat, col_index, count in compute_count_markers(notes, max_beat):
        if col_index < 0 or col_index >= len(columns):
            continue
        col = columns[int(col_index)]
        y = _beat_to_y(beat, int(col_index))
        ax.text(
            col.pixel_right + MARKER_MARGIN_PX,
            y,
            str(count),
            ha="left",
            va=_edge_va(y, col),
            fontproperties=get_font(7.0),
            color=COUNT_TEXT_COLOR,
            zorder=MARKER_ZORDER,
        )


def render_overlap_markers(
    ax: Axes,
    notes: list[NoteRenderInfo],
    threshold_x: float = NOTE_OVERLAP_THRESHOLD_X,
) -> None:
    """在开始时间重合的 Note 组旁边标注 "×n"。

    标注写在组最右 Note 的右侧（栏内，紧挨 Note 图标），
    垂直位置为组内 Note 的开始时间（组内同刻，y 相同）。
    """
    for group in compute_overlap_groups(notes, threshold_x):
        x = max(n.x_pixel for n in group) + NOTE_OVERLAP_LABEL_OFFSET_PX
        y = group[0].y_pixel
        ax.text(
            x,
            y,
            f"×{len(group)}",
            ha="left",
            va="center",
            fontproperties=get_font(8.0),
            color=MARKER_TEXT_COLOR,
            zorder=MARKER_ZORDER,
        )
