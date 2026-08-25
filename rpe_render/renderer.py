"""主渲染协调器：编排所有模块，执行完整渲染流程并输出 PNG。"""

from __future__ import annotations

import logging
from math import ceil, cos, radians

import matplotlib

matplotlib.use("Agg")  # 无显示环境下也可渲染
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from .affected_area_renderer import (
    affected_column_indices,
    build_affected_segments,
    render_affected_areas,
    render_affected_boxes,
)
from .background import (
    apply_background_to_canvas,
    apply_preview_overlay,
    apply_track_overlays,
    load_and_blur_background,
)
from .chart_parser import parse_chart, validate_chart
from .constants import (
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    COLUMN_WIDTH,
    INFO_BAR_HEIGHT_PX,
    OUTPUT_DPI,
    PREVIEW_BG_ALPHA,
    SIDE_MARKER_PADDING_PX,
    TRACK_BG_ALPHA,
)
from .easing.event_evaluator import judge_line_rotate_at, judge_line_x_at
from .grid_renderer import render_grid
from .hold_renderer import (
    prepare_hold_render_info,
    render_hold_body,
    render_hold_head_end,
    render_hold_trajectory,
)
from .info_bar import compute_duration_seconds, compute_note_stats, render_info_bar
from .marker_renderer import render_markers, render_overlap_markers
from .models import ColumnInfo, NoteRenderInfo
from .note_renderer import (
    NoteImageLoader,
    detect_multitap_groups,
    note_zorder_key,
    place_notes_on_axes,
)
from .timeline import (
    beat_to_pixel,
    compute_canvas_size,
    compute_columns,
    compute_max_beat,
    merge_all_notes,
    x_to_pixel,
)

logger = logging.getLogger("rpe_render")


class RenderConfig:
    """渲染配置"""

    def __init__(
        self,
        chart_path: str | object,
        background_path: str | object | None = None,
        output_path: str | object = "output.png",
        notes_dir: str | object = "resources/notes",
        dpi: int = OUTPUT_DPI,
        preview_bg_alpha: float = PREVIEW_BG_ALPHA,
        track_bg_alpha: float = TRACK_BG_ALPHA,
    ):
        self.chart_path = chart_path
        self.background_path = background_path
        self.output_path = output_path
        self.notes_dir = notes_dir
        self.dpi = dpi
        # 谱面预览区半透明黑色底色透明度（0.0 ~ 1.0）
        self.preview_bg_alpha = min(max(preview_bg_alpha, 0.0), 1.0)
        # 每条 Note 轨道区域额外加深透明度（0.0 ~ 1.0）
        self.track_bg_alpha = min(max(track_bg_alpha, 0.0), 1.0)


def _create_figure(columns: list[ColumnInfo], dpi: int) -> tuple[Figure, Axes, Axes]:
    """创建 Figure、主时间轴 Axes 与底部信息栏 Axes。"""
    canvas_w_in, canvas_h_in = compute_canvas_size(columns)
    fig = plt.figure(figsize=(canvas_w_in, canvas_h_in), dpi=dpi)

    total_height_px = COLUMN_BEATS * BEAT_HEIGHT_PX + INFO_BAR_HEIGHT_PX
    info_frac = INFO_BAR_HEIGHT_PX / total_height_px

    ax_info = fig.add_axes([0.0, 0.0, 1.0, info_frac])
    ax_main = fig.add_axes([0.0, info_frac, 1.0, 1.0 - info_frac])

    # xlim 两侧各预留标记边距，避免首栏左侧 / 末栏右侧的标记文字被裁剪
    # （末栏若为受影响栏，其右侧小区域超出常规边界，一并纳入）
    ax_main.set_xlim(
        -SIDE_MARKER_PADDING_PX,
        columns[-1].pixel_right
        + columns[-1].pixel_gap_right
        + SIDE_MARKER_PADDING_PX,
    )
    ax_main.set_ylim(0, COLUMN_BEATS * BEAT_HEIGHT_PX)
    ax_main.axis("off")
    # 信息栏与主区共用同一像素坐标空间（xlim 与主区一致，ylim 为信息栏高度），
    # 使整图背景曲绘能按像素精确切片铺到信息栏
    ax_info.set_xlim(
        -SIDE_MARKER_PADDING_PX,
        columns[-1].pixel_right
        + columns[-1].pixel_gap_right
        + SIDE_MARKER_PADDING_PX,
    )
    ax_info.set_ylim(0, INFO_BAR_HEIGHT_PX)
    ax_info.axis("off")

    # 显式固定 Axes 层级：主区绘制在信息栏之上。栏底部的 Note 贴图
    # 关闭了裁剪（见 note_renderer / hold_renderer），可越过两区交界
    # 绘制在信息栏顶部边框之上，避免最下方 Note 下半部分被边框遮挡
    ax_info.set_zorder(1)
    ax_main.set_zorder(2)

    return fig, ax_main, ax_info


def render(config: RenderConfig) -> None:
    """执行完整的谱面预览图渲染流程。

    主流程:
        1. 解析谱面 → ChartData
        2. 合并 Notes / 计算总拍数 / 统计
        3. 构建 NoteRenderInfo（多层 X 叠加 + 角度修正计算 true_x）：
           3a. 先算角度修正落点与栏索引（纯 beat 数学），检测受影响段 →
               受影响栏集合 → 分栏（受影响栏右侧额外间距）；
           3b. 再回填像素坐标（依赖分栏几何，与 3a 解耦避免循环依赖）
        4. 创建画布 → 背景 → 网格 → 受影响白框 → Hold → 标记 →
           受影响小区域 → 重合标注 → Note 贴图 → Hold Head/End
        5. 渲染底部信息栏并保存 PNG
    """
    # ===== Phase 1: 解析 =====
    chart = parse_chart(config.chart_path)
    issues = validate_chart(chart)
    for issue in issues:
        logger.warning("Validation: %s", issue)

    # ===== Phase 2: 计算 =====
    all_pairs = merge_all_notes(chart)
    all_notes = [n for n, _ in all_pairs]
    max_beat = compute_max_beat(chart)
    note_counts = compute_note_stats(all_notes)
    duration_sec = compute_duration_seconds(chart)

    multitap_set = detect_multitap_groups(all_notes)

    image_loader = NoteImageLoader(config.notes_dir)

    # ===== Phase 3a: Note 渲染信息准备（角度修正 + 栏索引，纯 beat 数学）=====
    # 栏数只由 max_beat 决定（受影响栏只影响像素几何，不影响栏数）
    num_columns = max(1, int(ceil(max_beat / COLUMN_BEATS)))
    notes_info: list[NoteRenderInfo] = []
    flat_index = 0
    for line in chart.judge_line_list:
        for note in line.notes:
            t_beat = note.start_time_beat
            angle = judge_line_rotate_at(line, t_beat)
            # ★ 旋转修正: true_x = 判定线 X + positionX·cos(角度)
            true_x = judge_line_x_at(line, t_beat) + note.position_x * cos(
                radians(angle)
            )
            col = min(int(t_beat // COLUMN_BEATS), num_columns - 1)

            notes_info.append(
                NoteRenderInfo(
                    note=note,
                    true_x=true_x,
                    beat=t_beat,
                    end_beat=note.end_time_beat,
                    is_multitap=(flat_index in multitap_set),
                    judge_line_name=line.name,
                    column=col,
                    x_pixel=0.0,
                    y_pixel=0.0,
                    y_pixel_end=0.0,
                    judge_line=line,
                    line_angle=angle,
                )
            )
            flat_index += 1

    # 受影响段检测 → 受影响栏集合 → 分栏（受影响栏右侧额外间距）
    segments = build_affected_segments(notes_info)
    affected_columns = affected_column_indices(segments)
    columns = compute_columns(max_beat, affected_columns)

    # ===== Phase 3b: 回填像素坐标（依赖分栏几何）=====
    for info in notes_info:
        info.x_pixel = x_to_pixel(info.true_x, columns[info.column].pixel_left)
        _, info.y_pixel, _ = beat_to_pixel(info.beat, columns)
        _, info.y_pixel_end, _ = beat_to_pixel(info.end_beat, columns)

    # Hold Head/End 贴图实际高度（供 Body 无缝衔接计算）
    head_img = image_loader.get_note_image(2, is_hl=False)
    end_img = image_loader.get_hold_end_image(is_hl=False)

    # ===== Phase 4: 画布创建 + 渲染 =====
    fig, ax, ax_info = _create_figure(columns, config.dpi)

    # 画布宽度包含两侧标记边距（背景与覆盖层需铺满整个坐标范围）
    canvas_w_px = (
        columns[-1].pixel_right
        + columns[-1].pixel_gap_right
        + 2 * SIDE_MARKER_PADDING_PX
    )
    canvas_h_px = COLUMN_BEATS * BEAT_HEIGHT_PX

    # [可选] 背景：模糊曲绘按总画布（主区 + 信息栏）整体裁剪后
    # 切片铺满两个 Axes，保证整图背景连续一致
    has_background = False
    if config.background_path:
        bg = load_and_blur_background(config.background_path)
        if bg is not None:
            apply_background_to_canvas(
                ax,
                ax_info,
                bg,
                canvas_w_px,
                canvas_h_px,
                INFO_BAR_HEIGHT_PX,
                x_min=-SIDE_MARKER_PADDING_PX,
            )
            has_background = True

    # 谱面预览区半透明黑色底色（可配置透明度）
    apply_preview_overlay(
        ax,
        canvas_w_px,
        canvas_h_px,
        alpha=config.preview_bg_alpha,
        x_min=-SIDE_MARKER_PADDING_PX,
    )

    # 每条 Note 轨道区域额外加深（不含轨道间隔栏），提高轨道区分度
    apply_track_overlays(
        ax,
        columns,
        canvas_h_px,
        alpha=config.track_bg_alpha,
    )

    # 网格与标记
    render_grid(ax, columns, chart.bpm_list)

    # 受影响段圆角白框（网格之上、Hold/Note 之下）
    render_affected_boxes(ax, columns, segments, image_loader)

    # Hold 渲染（Body/轨迹在 Note 贴图下方）
    hold_notes = [ni for ni in notes_info if ni.note.type == 2]
    judge_lines_dict = {line.name: line for line in chart.judge_line_list}
    hold_infos = prepare_hold_render_info(
        hold_notes,
        judge_lines_dict,
        columns,
        head_img_height=float(head_img.shape[0]),
        end_img_height=float(end_img.shape[0]),
    )
    for hi in hold_infos:
        render_hold_body(ax, hi, image_loader)
        render_hold_trajectory(ax, hi)

    # 右侧标记（时值间隔 + 累计计数），在 Note 之上
    render_markers(ax, columns, notes_info)

    # 受影响栏水平分布小区域（背景与主栏轨道一致，内容与 Note 同级）
    render_affected_areas(
        ax,
        columns,
        segments,
        image_loader,
        track_bg_alpha=config.track_bg_alpha,
    )

    # 位置重合的 Note 组标注 "×n"（写在 Note 旁边）
    render_overlap_markers(ax, notes_info)

    # Note 贴图（按 startTime 从早到晚分配递增 zorder，同刻 Hold 排前）
    place_notes_on_axes(ax, notes_info, image_loader)

    # zorder 映射：Hold Head/End 与普通 Note 使用同一排序键（bug #1）
    sorted_infos = sorted(notes_info, key=note_zorder_key)
    zorder_map = {id(info): 10 + idx for idx, info in enumerate(sorted_infos)}
    for hi in hold_infos:
        render_hold_head_end(
            ax,
            hi,
            image_loader,
            zorder=zorder_map.get(id(hi.note_info), 11),
        )

    # 底部信息栏（canvas_w_px 含两侧标记边距，与背景坐标一致）
    render_info_bar(
        ax_info,
        chart,
        note_counts,
        duration_sec,
        canvas_w_px,
    )

    # ===== Phase 5: 输出 =====
    fig.savefig(
        config.output_path,
        dpi=config.dpi,
        transparent=not has_background,
    )
    plt.close(fig)
    logger.info("Rendered chart preview to %s", config.output_path)


__all__ = ["RenderConfig", "render"]
