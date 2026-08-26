"""主渲染协调器：编排所有模块，执行完整渲染流程并输出图片。"""

from __future__ import annotations

import logging
from math import ceil, cos, radians
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无显示环境下也可渲染
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from PIL import Image

from .affected_area_renderer import (
    affected_column_indices,
    build_affected_segments,
    compute_affected_area_widths,
    render_affected_areas,
    render_affected_boxes,
)
from .background import (
    apply_preview_overlay,
    apply_track_overlays,
    load_and_blur_background,
    save_rendered_image,
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
from .easing.event_evaluator import judge_line_pose_at
from .grid_renderer import render_grid
from .hold_renderer import (
    prepare_hold_render_info,
    render_hold_body,
    render_hold_trajectory,
)
from .info_bar import compute_duration_seconds, compute_note_stats, render_info_bar
from .marker_renderer import render_markers, render_overlap_markers
from .models import ColumnInfo, NoteRenderInfo
from .note_renderer import (
    NoteImageLoader,
    composite_note_sprites,
    detect_multitap_groups_at_beats,
    note_zorder_key,
    place_note_sprites_on_axes,
)
from .timeline import (
    beat_to_pixel,
    compute_canvas_size,
    compute_columns,
    compute_max_beat,
    map_line_beat,
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
        output_format: str | None = None,
        notes_dir: str | object = "resources/notes",
        dpi: int = OUTPUT_DPI,
        preview_bg_alpha: float = PREVIEW_BG_ALPHA,
        track_bg_alpha: float = TRACK_BG_ALPHA,
    ):
        self.chart_path = chart_path
        self.background_path = background_path
        self.output_path = output_path
        self.output_format = _normalize_output_format(output_format, output_path)
        self.notes_dir = notes_dir
        self.dpi = dpi
        # 谱面预览区半透明黑色底色透明度（0.0 ~ 1.0）
        self.preview_bg_alpha = min(max(preview_bg_alpha, 0.0), 1.0)
        # 每条 Note 轨道区域额外加深透明度（0.0 ~ 1.0）
        self.track_bg_alpha = min(max(track_bg_alpha, 0.0), 1.0)


def _normalize_output_format(
    output_format: str | None, output_path: str | object
) -> str:
    """归一化输出格式；未指定时从输出文件扩展名推断。"""
    value = output_format
    if value is None:
        suffix = Path(str(output_path)).suffix.lower().lstrip(".")
        value = suffix or "png"
    normalized = str(value).lower().lstrip(".")
    if normalized == "jpeg":
        normalized = "jpg"
    if normalized not in {"png", "jpg"}:
        raise ValueError(
            f"Unsupported output format: {value!r}; expected 'png' or 'jpg'"
        )
    return normalized


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

    image_loader = NoteImageLoader(config.notes_dir)

    # ===== Phase 3a: Note 渲染信息准备（角度修正 + 栏索引，纯 beat 数学）=====
    # 栏数只由 max_beat 决定（受影响栏只影响像素几何，不影响栏数）
    num_columns = max(1, int(ceil(max_beat / COLUMN_BEATS)))
    notes_info: list[NoteRenderInfo] = []
    for line_index, line in enumerate(chart.judge_line_list):
        for note in line.notes:
            local_beat = note.start_time_beat
            local_end_beat = note.end_time_beat
            t_beat = map_line_beat(line, local_beat)
            end_beat = map_line_beat(line, local_end_beat)
            pose = judge_line_pose_at(chart, line_index, local_beat)
            # 判定线上的 Note 沿判定线 X 轴落点；世界姿态负责父线变换。
            true_x = pose.x + note.position_x * cos(radians(pose.angle))
            col = min(int(t_beat // COLUMN_BEATS), num_columns - 1)

            notes_info.append(
                NoteRenderInfo(
                    note=note,
                    true_x=true_x,
                    beat=t_beat,
                    end_beat=end_beat,
                    is_multitap=False,
                    judge_line_name=line.name,
                    column=col,
                    x_pixel=0.0,
                    y_pixel=0.0,
                    y_pixel_end=0.0,
                    judge_line=line,
                    line_angle=pose.angle,
                    local_beat=local_beat,
                    local_end_beat=local_end_beat,
                    line_index=line_index,
                    chart=chart,
                )
            )
    # BPM 因数会改变不同判定线 Note 的实际出现时刻；多押应按映射后的
    # 主谱面拍数判断，而不是只比较各自原始 TimeT。
    multitap_set = detect_multitap_groups_at_beats(notes_info)
    for index, info in enumerate(notes_info):
        info.is_multitap = index in multitap_set

    # 受影响段检测 → 受影响栏集合 → 各栏小区域宽度（真实间距占用）→ 分栏
    # （受影响栏右侧额外间距按区域宽度动态放大）
    segments = build_affected_segments(notes_info)
    affected_columns = affected_column_indices(segments)
    column_area_widths = compute_affected_area_widths(segments)
    columns = compute_columns(max_beat, affected_columns, column_area_widths)

    # ===== Phase 3b: 回填像素坐标（依赖分栏几何）=====
    for info in notes_info:
        info.x_pixel = x_to_pixel(info.true_x, columns[info.column].pixel_left)
        _, info.y_pixel, _ = beat_to_pixel(info.beat, columns)
        _, info.y_pixel_end, _ = beat_to_pixel(info.end_beat, columns)

    # Hold Head/End 贴图实际高度（供 Body 无缝衔接计算）
    head_img = image_loader.get_note_image(2, is_hl=False)
    head_img_hl = image_loader.get_note_image(2, is_hl=True)
    end_img = image_loader.get_hold_end_image(is_hl=False)
    end_img_hl = image_loader.get_hold_end_image(is_hl=True)

    # ===== Phase 4: 画布创建 + 渲染 =====
    fig, ax, ax_info = _create_figure(columns, config.dpi)

    # 画布宽度包含两侧标记边距（背景与覆盖层需铺满整个坐标范围）
    canvas_w_px = (
        columns[-1].pixel_right
        + columns[-1].pixel_gap_right
        + 2 * SIDE_MARKER_PADDING_PX
    )
    canvas_h_px = COLUMN_BEATS * BEAT_HEIGHT_PX

    # [可选] 背景只在此处加载。Matplotlib 始终渲染透明前景，曲绘在
    # Phase 5 由 Pillow 一次性合成，避免长谱面的背景分块产生大量 artist。
    bg = None
    if config.background_path:
        bg = load_and_blur_background(config.background_path)

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
        head_img_height_hl=float(head_img_hl.shape[0]),
        end_img_height_hl=float(end_img_hl.shape[0]),
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

    # 普通 Note 与 Hold Head/End 共用排序和批处理路径。大谱面按栏合成为
    # 少量 RGBA artist；小谱面保留逐图路径，避免透明整栏的固定成本。
    sorted_infos = sorted(notes_info, key=note_zorder_key)
    zorder_map = {id(info): 10 + idx for idx, info in enumerate(sorted_infos)}
    deferred_note_sprites = place_note_sprites_on_axes(
        ax, notes_info, hold_infos, image_loader, zorder_map
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
    # 直接读取 Agg 的 RGBA 缓冲区，避免先编码一遍临时 PNG。copy() 使前景
    # 脱离 Matplotlib 画布，随后即可尽早释放 figure/artist 占用的内存。
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    ax_info.patch.set_alpha(0.0)
    try:
        fig.canvas.draw()
        foreground = Image.frombuffer(
            "RGBA",
            fig.canvas.get_width_height(),
            fig.canvas.buffer_rgba(),
            "raw",
            "RGBA",
            0,
            1,
        ).copy()
        composite_note_sprites(foreground, ax, deferred_note_sprites)
    finally:
        plt.close(fig)

    save_rendered_image(
        foreground,
        config.output_path,
        config.output_format,
        bg_image=bg,
    )
    logger.info("Rendered chart preview to %s", config.output_path)


__all__ = ["RenderConfig", "render"]
