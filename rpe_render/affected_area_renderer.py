"""受影响段（近竖直判定线）的特殊渲染：圆角空心白框 + 栏右侧水平分布小区域。

判定线角度绝对值在 [AFFECTED_ANGLE_MIN_DEG, AFFECTED_ANGLE_MAX_DEG] 内时，
note 的落点压缩在判定线附近，几乎看不出水平走向。对这类段在主栏绘制空心
圆角白框提示，并在受影响栏右侧的小区域中渲染水平分布；小区域背景与主栏
轨道一致（半透明黑覆盖层），高度与受影响区域等高。

本模块不依赖其他渲染模块；image_loader 以鸭子类型传入（与 hold_renderer 相同）。
背景 zorder 常量复用 background.TRACK_BG_ZORDER，保证与主栏轨道同层。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians
from typing import Any, Callable

from matplotlib.axes import Axes
from matplotlib.patches import FancyBboxPatch, Rectangle

from .background import TRACK_BG_ZORDER
from .constants import (
    AFFECTED_ANGLE_MAX_DEG,
    AFFECTED_ANGLE_MIN_DEG,
    AFFECTED_AREA_BORDER_COLOR,
    AFFECTED_AREA_MARGIN_LEFT_PX,
    AFFECTED_BOX_CLUSTER_GAP_BEATS,
    AFFECTED_BOX_EDGE_COLOR,
    AFFECTED_BOX_PAD_X_PX,
    AFFECTED_BOX_PAD_Y_PX,
    AFFECTED_BOX_ROUNDING_PX,
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    COLUMN_WIDTH,
    GAME_X_MAX,
    GAME_X_MIN,
    HOLD_BODY_OVERLAP_PX,
    NOTE_ICON_WIDTH,
    TRACK_BG_ALPHA,
)
from .easing.event_evaluator import judge_line_rotate_at, judge_line_x_at
from .models import ColumnInfo, NoteRenderInfo
from .timeline import x_to_pixel

# 白框描边 zorder：网格（0）之上、Hold Body（2）/ 轨迹（6）/ Note（10+）之下
AFFECTED_BG_ZORDER = 1

# 区域内 Note 内容与主栏 Note 同级（NOTE_BASE_ZORDER + 递增）
NOTE_BASE_ZORDER = 10


@dataclass
class AffectedSegment:
    """一段时间上连续的受影响 note（同一判定线）。

    notes 按 beat 升序排列（含跨栏 note）；beat_end 对 Hold 段包含其 end_beat。
    """

    judge_line: object  # 判定线引用（无引用时退化为名称字符串）
    notes: list[NoteRenderInfo]
    beat_start: float
    beat_end: float


def _normalize_angle(deg: float) -> float:
    """将角度归一化到 [-180, 180]（270° 等价 -90°，参与阈值判定）。"""
    norm = deg % 360.0
    if norm > 180.0:
        norm -= 360.0
    return norm


def _is_affected(note: NoteRenderInfo, min_deg: float, max_deg: float) -> bool:
    return min_deg <= abs(_normalize_angle(note.line_angle)) <= max_deg


def _note_end_beat(note: NoteRenderInfo) -> float:
    """note 覆盖到的最晚拍数（Hold 用 end_beat，其余用 beat）。"""
    return note.end_beat if note.note.type == 2 else note.beat


def build_affected_segments(
    notes_info: list[NoteRenderInfo],
    min_deg: float = AFFECTED_ANGLE_MIN_DEG,
    max_deg: float = AFFECTED_ANGLE_MAX_DEG,
) -> list[AffectedSegment]:
    """聚合时间上连续的受影响 note 为段。

    规则：
    1. 按判定线分组（judge_line 引用优先，judge_line_name 兜底）；
    2. 组内按 beat 升序排序；
    3. 角度绝对值在 [min_deg, max_deg] 内的 note 标记为受影响；
    4. 连续的受影响 note 聚合为一段；中间夹未受影响 note 则断段；
       Hold 按 startTime 判定，段范围包含其 end_beat。

    Returns:
        受影响段列表（按判定线分组的发现顺序，段内 notes 按 beat 升序）。
    """
    groups: dict[object, tuple[object, list[NoteRenderInfo]]] = {}
    for n in notes_info:
        if n.judge_line is not None:
            key = ("line", id(n.judge_line))  # 判定线对象不可哈希，用 id() 分组
            ref: object = n.judge_line
        else:
            key = ("name", n.judge_line_name)  # 无引用时按名称兜底
            ref = n.judge_line_name
        groups.setdefault(key, (ref, []))[1].append(n)

    segments: list[AffectedSegment] = []
    for _, (line, notes) in groups.items():
        current: AffectedSegment | None = None
        for n in sorted(notes, key=lambda x: x.beat):
            if _is_affected(n, min_deg, max_deg):
                if current is None:
                    current = AffectedSegment(
                        judge_line=line,
                        notes=[n],
                        beat_start=n.beat,
                        beat_end=_note_end_beat(n),
                    )
                    segments.append(current)
                else:
                    current.notes.append(n)
                    current.beat_end = max(current.beat_end, _note_end_beat(n))
            else:
                current = None  # 夹在中间的未受影响 note 断开当前段
    return segments


def affected_column_indices(segments: list[AffectedSegment]) -> set[int]:
    """受影响段覆盖的所有栏索引。

    每个 note 计入其 column；Hold 再按 end_beat 补齐跨过的所有栏。
    """
    cols: set[int] = set()
    for seg in segments:
        for n in seg.notes:
            cols.add(n.column)
            if n.note.type == 2:
                cols.update(
                    range(
                        int(n.beat // COLUMN_BEATS),
                        int(n.end_beat // COLUMN_BEATS) + 1,
                    )
                )
    return cols


def _note_covers_column(note_info: NoteRenderInfo, col_index: int) -> bool:
    """note 是否覆盖指定栏（Hold 按 [start 栏, end 栏] 覆盖，其余仅本栏）。"""
    if note_info.note.type == 2:
        return (
            int(note_info.beat // COLUMN_BEATS)
            <= col_index
            <= int(note_info.end_beat // COLUMN_BEATS)
        )
    return note_info.column == col_index


def _note_x_in_column(
    note_info: NoteRenderInfo,
    col_index: int,
    columns: list[ColumnInfo],
) -> float:
    """note 在指定栏内的有效像素 X。

    跨栏 Hold 在非起始栏的 X 不能沿用起始栏的 x_pixel，须按本栏起始时刻的
    判定线落点（含角度修正）重新计算（与 hold_renderer 的分段逻辑一致）。
    """
    if note_info.note.type == 2 and col_index != note_info.column:
        line = note_info.judge_line
        t = max(note_info.beat, col_index * COLUMN_BEATS)
        if line is not None:
            jl_x = judge_line_x_at(line, t)
            angle = judge_line_rotate_at(line, t)
        else:
            jl_x = 0.0
            angle = 0.0
        true_x = jl_x + note_info.note.position_x * cos(radians(angle))
        return x_to_pixel(true_x, columns[col_index].pixel_left)
    return note_info.x_pixel


def _split_into_clusters(
    notes: list[NoteRenderInfo],
    gap_beats: float,
) -> list[list[NoteRenderInfo]]:
    """将按 beat 升序排列的受影响 note 按间隔聚类。

    相邻 note（相对于上一个 note 的结束拍）间隔 > gap_beats 时拆成新簇；
    每个簇内的时间范围紧贴音符，避免白框框出无 note 的段落。

    Args:
        notes: beat 升序的受影响 note（须同一栏）
        gap_beats: 拆簇阈值（拍）

    Returns:
        簇列表（每簇保持 beat 升序）
    """
    clusters: list[list[NoteRenderInfo]] = []
    current: list[NoteRenderInfo] = []
    for n in notes:
        if current and n.beat - _note_end_beat(current[-1]) > gap_beats:
            clusters.append(current)
            current = [n]
        else:
            current.append(n)
    if current:
        clusters.append(current)
    return clusters


def _rect_overlaps(a: tuple, b: tuple) -> bool:
    """两矩形 (x0, y0, x1, y1) 是否相交或相接。"""
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _merge_overlapping_rects(
    rects: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """合并所有相交/相接的矩形为包围盒并集。"""
    merged = list(rects)
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                if _rect_overlaps(merged[i], merged[j]):
                    a, b = merged[i], merged[j]
                    merged[i] = (
                        min(a[0], b[0]),
                        min(a[1], b[1]),
                        max(a[2], b[2]),
                        max(a[3], b[3]),
                    )
                    del merged[j]
                    changed = True
                    break
            if changed:
                break
    return merged


def render_affected_boxes(
    ax: Axes,
    columns: list[ColumnInfo],
    segments: list[AffectedSegment],
    image_loader: Any,
) -> None:
    """为每段在受影响的栏内绘制圆角空心白框（zorder=1，网格之上）。

    每条受影响 note 簇（相邻间隔 <= AFFECTED_BOX_CLUSTER_GAP_BEATS，按栏截断）
    生成一个候选框；同一栏内相互重合的候选框合并为一个（包围盒并集），
    避免多线同刻的重叠白框重复描边，观感更清爽。仅描边不填充（空心白框）。

    横向 = 簇内 note 在该栏的 x_pixel 极值 ±（图标半宽 + AFFECTED_BOX_PAD_X_PX）；
    纵向 = 簇起拍~结束拍（Hold 含 end_beat，与栏范围求交）± AFFECTED_BOX_PAD_Y_PX。
    """
    del image_loader  # 图标半宽由常量确定，无需读取贴图
    half_icon = NOTE_ICON_WIDTH / 2.0

    rects: list[tuple[float, float, float, float]] = []
    for seg in segments:
        for col in columns:
            column_notes = [
                n for n in seg.notes if _note_covers_column(n, col.index)
            ]
            if not column_notes:
                continue
            for cluster in _split_into_clusters(
                column_notes, AFFECTED_BOX_CLUSTER_GAP_BEATS
            ):
                c_start = max(cluster[0].beat, col.beat_start)
                c_end = min(
                    max(_note_end_beat(n) for n in cluster), col.beat_end
                )
                if c_end < c_start:
                    continue
                xs = [_note_x_in_column(n, col.index, columns) for n in cluster]
                rects.append(
                    (
                        min(xs) - half_icon - AFFECTED_BOX_PAD_X_PX,
                        (c_start - col.beat_start) * BEAT_HEIGHT_PX
                        - AFFECTED_BOX_PAD_Y_PX,
                        max(xs) + half_icon + AFFECTED_BOX_PAD_X_PX,
                        (c_end - col.beat_start) * BEAT_HEIGHT_PX
                        + AFFECTED_BOX_PAD_Y_PX,
                    )
                )

    for x0, y0, x1, y1 in _merge_overlapping_rects(rects):
        ax.add_patch(
            FancyBboxPatch(
                (x0, y0),
                x1 - x0,
                y1 - y0,
                boxstyle=f"round,pad=0,rounding_size={AFFECTED_BOX_ROUNDING_PX}",
                facecolor="none",
                edgecolor=AFFECTED_BOX_EDGE_COLOR,
                linewidth=1.0,
                zorder=AFFECTED_BG_ZORDER,
            )
        )


def compute_affected_area_widths(
    segments: list[AffectedSegment],
) -> dict[int, float]:
    """每个受影响栏的小区域宽度：栏内受影响 note 的真实横向占用宽度。

    宽度 = 最左 note 左端到最右 note 右端 = positionX 跨度按主栏同比例
    （GAME_X 全宽 1350 单位 → COLUMN_WIDTH px）换算 + 单个图标宽度。
    跨栏 Hold 按其覆盖的每栏计入（各段 X 均由 positionX 决定）。

    Returns:
        {栏索引: 区域宽度(px)}，仅含有关注 note 的受影响栏。
    """
    scale = COLUMN_WIDTH / (GAME_X_MAX - GAME_X_MIN)
    widths: dict[int, float] = {}
    for col_index in sorted(affected_column_indices(segments)):
        px = [
            n.note.position_x
            for seg in segments
            for n in seg.notes
            if _note_covers_column(n, col_index)
        ]
        if not px:
            continue
        widths[col_index] = (max(px) - min(px)) * scale + NOTE_ICON_WIDTH
    return widths


def _make_area_x(
    area_left: float,
    p_min: float,
    scale: float,
) -> Callable[[float], float]:
    """区域内水平坐标映射：按真实间距（与主栏同比例）放置图标中心。

    最左 note 的左端对齐区域左缘；note 之间的像素距离 = positionX 差 × scale，
    与主栏中相同 note 的横向距离完全一致（不再固定宽度压缩）。
    """

    def area_x(position_x: float) -> float:
        return area_left + (position_x - p_min) * scale + NOTE_ICON_WIDTH / 2.0

    return area_x


def _hold_segment_geometry(
    note_info: NoteRenderInfo,
    col_index: int,
) -> tuple[float, float, float, float, bool, bool]:
    """Hold 在指定栏内的分段几何（仿照 hold_renderer.prepare_hold_render_info）。

    Returns:
        (seg_start, seg_end, y_head, y_end, has_head, has_end)
    """
    col_base = col_index * COLUMN_BEATS
    seg_start = max(note_info.beat, col_base)
    seg_end = min(note_info.end_beat, col_base + COLUMN_BEATS)
    y_head = (seg_start - col_base) * BEAT_HEIGHT_PX
    y_end = (seg_end - col_base) * BEAT_HEIGHT_PX
    has_head = col_index == int(note_info.beat // COLUMN_BEATS)
    has_end = col_index == int(note_info.end_beat // COLUMN_BEATS)
    return seg_start, seg_end, y_head, y_end, has_head, has_end


def _draw_icon(
    ax: Axes,
    image_loader: Any,
    note_info: NoteRenderInfo,
    col_index: int,
    area_x: Callable[[float], float],
    zorder: float,
) -> None:
    """区域内绘制一个普通 Note 图标（X 由真实间距映射）。"""
    img = image_loader.get_note_image(note_info.note.type, note_info.is_multitap)
    h, w = img.shape[0], img.shape[1]
    cx = area_x(note_info.note.position_x)
    cy = (note_info.beat - col_index * COLUMN_BEATS) * BEAT_HEIGHT_PX
    ax.imshow(
        img,
        extent=[cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2],
        zorder=zorder,
        interpolation="bilinear",
    )


def _draw_hold_piece(
    ax: Axes,
    image_loader: Any,
    note_info: NoteRenderInfo,
    col_index: int,
    area_x: Callable[[float], float],
    zorder: float,
) -> None:
    """区域内绘制 Hold 在该栏的一段（Head/End/Body，X 全部由 positionX 映射）。"""
    _, _, y_head, y_end, has_head, has_end = _hold_segment_geometry(
        note_info, col_index
    )
    hl = note_info.is_multitap
    cx = area_x(note_info.note.position_x)
    half_w = NOTE_ICON_WIDTH / 2.0

    if has_head:
        img = image_loader.get_note_image(2, hl)
        h = img.shape[0]
        ax.imshow(
            img,
            extent=[cx - half_w, cx + half_w, y_head - h / 2, y_head + h / 2],
            zorder=zorder,
            interpolation="bilinear",
        )
        body_bottom = y_head + h / 2 - HOLD_BODY_OVERLAP_PX
    else:
        body_bottom = 0.0

    if has_end:
        img = image_loader.get_hold_end_image(hl)
        h = img.shape[0]
        ax.imshow(
            img,
            extent=[cx - half_w, cx + half_w, y_end - h / 2, y_end + h / 2],
            zorder=zorder,
            interpolation="bilinear",
        )
        body_top = y_end - h / 2 + HOLD_BODY_OVERLAP_PX
    else:
        body_top = COLUMN_BEATS * BEAT_HEIGHT_PX

    body_height = body_top - body_bottom
    if body_height > 0:
        body = image_loader.get_hold_body_image(2, hl, int(round(body_height)))
        ax.imshow(
            body,
            extent=[cx - half_w, cx + half_w, body_bottom, body_top],
            zorder=zorder,
            interpolation="bilinear",
        )


def _affected_extent_in_column(
    segments: list[AffectedSegment],
    col_index: int,
) -> tuple[float, float] | None:
    """受影响段在指定栏内的纵向拍数范围（与栏范围求交）。

    Returns:
        (t_start, t_end) 拍数；无受影响 note 或区间为空时返回 None。
    """
    covers = [
        n
        for seg in segments
        for n in seg.notes
        if _note_covers_column(n, col_index)
    ]
    if not covers:
        return None
    t0 = max(min(n.beat for n in covers), col_index * COLUMN_BEATS)
    t1 = min(
        max(_note_end_beat(n) for n in covers),
        (col_index + 1) * COLUMN_BEATS,
    )
    if t1 <= t0:
        return None
    return t0, t1


def render_affected_areas(
    ax: Axes,
    columns: list[ColumnInfo],
    segments: list[AffectedSegment],
    image_loader: Any,
    track_bg_alpha: float = TRACK_BG_ALPHA,
) -> None:
    """为每个受影响栏绘制水平分布小区域（背景 + 区域内 Note 内容）。

    区域位于栏右缘外侧（pixel_right + AFFECTED_AREA_MARGIN_LEFT_PX 起），
    宽度 = 栏内受影响 note 的真实横向占用宽度（最左 note 左端到最右 note
    右端，见 compute_affected_area_widths）；纵向仅覆盖该栏受影响段的范围
    （与受影响区域等高），不再填满整栏；背景与主栏轨道一致（半透明黑覆盖
    层，无白色填充）。note 按真实间距放置（与主栏同比例，不压缩），内容
    zorder 按 beat 排序 10+ 递增；同刻时 Hold 排前（zorder 更低），
    非 Hold Note 绘制在上层，避免 Hold 头遮挡与之重合的音符。
    """
    affected_cols = sorted(
        c for c in affected_column_indices(segments) if c < len(columns)
    )
    area_widths = compute_affected_area_widths(segments)
    scale = COLUMN_WIDTH / (GAME_X_MAX - GAME_X_MIN)

    for col_index in affected_cols:
        col = columns[col_index]
        area_left = col.pixel_right + AFFECTED_AREA_MARGIN_LEFT_PX
        width = area_widths.get(col_index, 0.0)
        if width <= 0.0:
            continue

        # 区域内真实间距映射：锚点为栏内受影响 note 的最小 positionX
        col_notes = [
            n
            for seg in segments
            for n in seg.notes
            if _note_covers_column(n, col_index)
        ]
        p_min = min(n.note.position_x for n in col_notes)
        area_x = _make_area_x(area_left, p_min, scale)

        # 背景与主栏轨道同款：半透明黑覆盖在预览区底色之上，仅描边区分区域；
        # 纵向仅覆盖该栏受影响段的范围（与受影响区域等高），高度为 0 时跳过
        extent = _affected_extent_in_column(segments, col_index)
        if extent is not None and track_bg_alpha > 0.0:
            t0, t1 = extent
            y0 = (t0 - col.beat_start) * BEAT_HEIGHT_PX
            y1 = (t1 - col.beat_start) * BEAT_HEIGHT_PX
            if y1 > y0:
                ax.add_patch(
                    Rectangle(
                        (area_left, y0),
                        width,
                        y1 - y0,
                        facecolor="black",
                        alpha=min(track_bg_alpha, 1.0),
                        linewidth=1.0,
                        edgecolor=AFFECTED_AREA_BORDER_COLOR,
                        zorder=TRACK_BG_ZORDER,
                    )
                )

        # jobs: (beat, 0=Hold 排前 / 1=普通 Note 排后, draw)；同刻普通 Note
        # 分配更高 zorder 绘制在上层，不被 Hold 头遮挡
        jobs: list[tuple[float, int, Callable[[float], None]]] = []
        for seg in segments:
            for n in seg.notes:
                if not _note_covers_column(n, col_index):
                    continue
                if n.note.type == 2:
                    jobs.append(
                        (
                            n.beat,
                            0,
                            lambda z, n=n: _draw_hold_piece(
                                ax, image_loader, n, col_index, area_x, z
                            ),
                        )
                    )
                else:
                    jobs.append(
                        (
                            n.beat,
                            1,
                            lambda z, n=n: _draw_icon(
                                ax, image_loader, n, col_index, area_x, z
                            ),
                        )
                    )

        for z, (_, _, draw) in enumerate(
            sorted(jobs, key=lambda t: (t[0], t[1]))
        ):
            draw(NOTE_BASE_ZORDER + z)


__all__ = [
    "AffectedSegment",
    "affected_column_indices",
    "build_affected_segments",
    "render_affected_areas",
    "render_affected_boxes",
]
