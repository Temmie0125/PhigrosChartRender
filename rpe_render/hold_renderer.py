"""Hold 音符渲染：Body 纵向拉伸、Head/End 贴图放置与轨迹曲线。

依赖 easing/event_evaluator 获取判定线各时刻的 X 坐标。
本模块不依赖其他渲染模块；image_loader 以鸭子类型传入。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians

import numpy as np
from matplotlib.axes import Axes

from .constants import (
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    HOLD_BODY_OVERLAP_PX,
    HOLD_TRAJECTORY_COLOR,
    HOLD_TRAJECTORY_MIN_DISPLACEMENT_PX,
    HOLD_TRAJECTORY_SAMPLES_PER_BEAT,
    HOLD_TRAJECTORY_WIDTH,
    NOTE_ICON_WIDTH,
)
from .easing.event_evaluator import judge_line_pose_at
from .models import ColumnInfo, JudgeLineData, NoteData, NoteRenderInfo
from .timeline import x_to_pixel

# Z 轴层次（见设计文档 4.12.3）
HOLD_BODY_ZORDER = 2
HOLD_TRAJECTORY_ZORDER = 6
HOLD_HEAD_END_DEFAULT_ZORDER = 11  # 与普通 Note 同层（NOTE_BASE_ZORDER + 1）

# Head/End 贴图的默认名义高度（无法获取真实贴图高度时的回退值）
_DEFAULT_IMG_HEIGHT = float(NOTE_ICON_WIDTH)


@dataclass
class HoldRenderInfo:
    """Hold 音符的完整渲染信息（一个分栏段）。

    一段 Hold 若跨越多个分栏，会被拆分为多个 HoldRenderInfo，
    每个段只在所属栏内绘制 Body 与轨迹；Head/End 贴图仅出现在
    包含 startTime / endTime 的段中。
    """

    note_info: NoteRenderInfo
    head_y: float  # Head 贴图中心 Y（顶部接合 startTime）
    end_y: float  # End 贴图中心 Y（底部接合 endTime）
    body_top_y: float  # Body 拉伸区域的顶部 Y
    body_bottom_y: float  # Body 拉伸区域的底部 Y
    body_height: float  # Body 需要拉伸的高度（px）
    trajectory_points: list[tuple[float, float]] | None  # 轨迹采样点 [(x_px, y_px), ...]
    x_pixel: float = 0.0  # 段内有效像素 X（Body/Head/End 对齐），已映射到本栏坐标
    has_head: bool = True  # 本段是否包含 Head 贴图
    has_end: bool = True  # 本段是否包含 End 贴图
    column_index: int = 0  # 本段所在分栏索引


def _column_floor(beat: float) -> float:
    """beat 所在栏的起始拍数。"""
    return float(int(beat // COLUMN_BEATS) * COLUMN_BEATS)


def _has_actual_displacement(
    points: list[tuple[float, float]],
    min_displacement_px: float = HOLD_TRAJECTORY_MIN_DISPLACEMENT_PX,
) -> bool:
    """轨迹采样点是否存在实际位移。

    以采样点像素 X 的极差（max - min）衡量：小于阈值视为无位移
    （轨迹与竖直 Body 完全重合），不渲染。

    Args:
        points: 轨迹采样点 [(x_px, y_px), ...]
        min_displacement_px: 最小位移阈值（px）
    """
    xs = [p[0] for p in points]
    return max(xs) - min(xs) >= min_displacement_px


def sample_hold_trajectory(
    line: JudgeLineData | None,
    note: NoteData,
    start_beat: float,
    end_beat: float,
    samples_per_beat: int,
    column_offset_px: float,
    *,
    chart: object | None = None,
    line_index: int = -1,
    display_start_beat: float | None = None,
    display_end_beat: float | None = None,
    display_factor: float = 1.0,
) -> list[tuple[float, float]]:
    """对 Hold 持续期间的判定线 X + note.positionX 进行采样。

    Args:
        line: 判定线数据（None 时按静止线处理，X=0）
        note: Hold 音符数据
        start_beat: 采样起始拍（须与 end_beat 同栏）
        end_beat: 采样结束拍
        samples_per_beat: 每拍采样点数
        column_offset_px: 栏左侧像素 X 偏移

    Returns:
        [(x_pixel, y_pixel), ...] 像素坐标列表（栏内坐标系）；
        duration <= 0 时返回空列表。
    """
    duration = end_beat - start_beat
    if duration <= 0:
        return []

    num_samples = max(2, int(duration * samples_per_beat))
    points: list[tuple[float, float]] = []
    if display_start_beat is None:
        display_start_beat = start_beat * display_factor
    if display_end_beat is None:
        display_end_beat = end_beat * display_factor
    display_duration = display_end_beat - display_start_beat
    col_base = _column_floor(display_start_beat)

    for i in range(num_samples + 1):
        t = start_beat + (duration * i / num_samples)
        if line is not None and chart is not None and line_index >= 0:
            pose = judge_line_pose_at(chart, line_index, t)
            jl_x = pose.x
            angle = pose.angle
        elif line is not None:
            # 兼容旧的无 ChartData 调用：按独立判定线处理。
            from .easing.event_evaluator import judge_line_x_at, judge_line_rotate_at

            jl_x = judge_line_x_at(line, t)
            angle = judge_line_rotate_at(line, t)
        else:
            jl_x = 0.0
            angle = 0.0
        # 旋转修正: true_x = 判定线 X + positionX·cos(角度)
        true_x = jl_x + note.position_x * cos(radians(angle))
        display_t = display_start_beat + display_duration * i / num_samples
        y_px = (display_t - col_base) * BEAT_HEIGHT_PX
        x_px = x_to_pixel(true_x, column_offset_px)
        points.append((x_px, y_px))

    return points


def prepare_hold_render_info(
    hold_notes: list[NoteRenderInfo],
    judge_lines: dict[str, JudgeLineData],
    columns: list[ColumnInfo],
    sample_density: int = HOLD_TRAJECTORY_SAMPLES_PER_BEAT,
    head_img_height: float = _DEFAULT_IMG_HEIGHT,
    end_img_height: float = _DEFAULT_IMG_HEIGHT,
    head_img_height_hl: float | None = None,
    end_img_height_hl: float | None = None,
) -> list[HoldRenderInfo]:
    """为所有 Hold 音符准备渲染信息（含跨栏拆分）。

    处理每个 Hold:
        1. 计算 Head 贴图 Y（startTime 对应的栏内像素 Y）
        2. 计算 End 贴图 Y（endTime 对应的栏内像素 Y，含真实 End X）
        3. 计算 Body 区域：Head 贴图底部 到 End 贴图顶部（按栏截断）
        4. 从 startTime 到 endTime 按 sample_density 采样轨迹曲线：
           每个采样点计算 judge_line_x_at(line, t) + positionX·cos(rotate(t)) → 像素 X

    Args:
        hold_notes: 所有 Hold 类型音符的 NoteRenderInfo
        judge_lines: 判定线字典（key=判定线名称），当 note_info 未携带
            判定线引用时按名称查找
        columns: 分栏信息
        sample_density: 每拍采样点数
        head_img_height: Head 贴图缩放后的实际高度（px）
        end_img_height: End 贴图缩放后的实际高度（px）
        head_img_height_hl: HL Head 贴图高度；未提供时沿用 head_img_height
        end_img_height_hl: HL End 贴图高度；未提供时沿用 end_img_height

    Returns:
        HoldRenderInfo 列表（跨栏 Hold 会产生多个条目）
    """
    infos: list[HoldRenderInfo] = []
    column_top = float(COLUMN_BEATS * BEAT_HEIGHT_PX)

    for info in hold_notes:
        # HL 贴图可能带有额外发光延伸，几何计算必须使用该音符实际采用
        # 的贴图高度，否则多押 Hold 的头尾会与 Body 产生错位。
        current_head_height = (
            head_img_height_hl
            if info.is_multitap and head_img_height_hl is not None
            else head_img_height
        )
        current_end_height = (
            end_img_height_hl
            if info.is_multitap and end_img_height_hl is not None
            else end_img_height
        )
        line = info.judge_line
        if line is None:
            line = judge_lines.get(info.judge_line_name)

        s, e = info.beat, info.end_beat
        factor = float(getattr(line, "bpm_factor", 1.0)) if line is not None else 1.0
        col_s = int(s // COLUMN_BEATS)
        col_e = int(e // COLUMN_BEATS)

        for col in range(col_s, col_e + 1):
            col_base = col * COLUMN_BEATS
            seg_start = max(s, col_base)
            seg_end = min(e, col_base + COLUMN_BEATS)

            y_head_seg = (seg_start - col_base) * BEAT_HEIGHT_PX
            y_end_seg = (seg_end - col_base) * BEAT_HEIGHT_PX

            # Body 的端点对齐 start/end 拍点；Head/End 贴图向端点外侧接合。
            head_y = y_head_seg - current_head_height / 2
            end_y = y_end_seg + current_end_height / 2

            has_head = col == col_s
            has_end = col == col_e

            # 段内有效 X（像素，映射到本栏坐标）：
            # - 含 Head 的段（即起始栏段）取 Note 开始位置，note_info.x_pixel 在该栏内有效
            # - 尾段/中段取本段起始时刻的判定线 X + positionX。
            #   ★ 不能用 note_info.x_pixel：它是 Note 起始栏的坐标，跨栏 Hold 的
            #   尾段若照用会被画进起始栏（bug: 跨 16 小节 Hold 被错误渲染到同一栏）
            col_offset = columns[col].pixel_left
            if has_head:
                seg_x_pixel = info.x_pixel
            else:
                if line is not None:
                    local_seg_start = seg_start / factor
                    if info.chart is not None and info.line_index >= 0:
                        pose = judge_line_pose_at(
                            info.chart, info.line_index, local_seg_start
                        )
                        seg_line_x = pose.x
                        seg_angle = pose.angle
                    else:
                        from .easing.event_evaluator import judge_line_x_at, judge_line_rotate_at

                        seg_line_x = judge_line_x_at(line, local_seg_start)
                        seg_angle = judge_line_rotate_at(line, local_seg_start)
                else:
                    seg_line_x = 0.0
                    seg_angle = 0.0
                seg_x_pixel = x_to_pixel(
                    seg_line_x + info.note.position_x * cos(radians(seg_angle)),
                    col_offset,
                )

            # Body 端点直接对齐 start/end 拍点；头尾各向贴图内侧延伸少量
            # HOLD_BODY_OVERLAP_PX，消除缩放后的抗锯齿接缝。
            body_bottom = y_head_seg - HOLD_BODY_OVERLAP_PX if has_head else 0.0
            body_top = y_end_seg + HOLD_BODY_OVERLAP_PX if has_end else column_top
            body_height = body_top - body_bottom

            trajectory = sample_hold_trajectory(
                line=line,
                note=info.note,
                start_beat=seg_start / factor,
                end_beat=seg_end / factor,
                samples_per_beat=sample_density,
                column_offset_px=col_offset,
                chart=info.chart,
                line_index=info.line_index,
                display_start_beat=seg_start,
                display_end_beat=seg_end,
                display_factor=factor,
            )
            # 设计文档：仅当 Hold 持续期间存在实际位移时才渲染运动轨迹。
            # 无位移时轨迹与竖直 Body 重合，置 None 跳过渲染。
            if trajectory and not _has_actual_displacement(trajectory):
                trajectory = None

            infos.append(
                HoldRenderInfo(
                    note_info=info,
                    head_y=head_y,
                    end_y=end_y,
                    body_top_y=body_top,
                    body_bottom_y=body_bottom,
                    body_height=body_height,
                    trajectory_points=trajectory if trajectory else None,
                    x_pixel=seg_x_pixel,
                    has_head=has_head,
                    has_end=has_end,
                    column_index=col,
                )
            )

    return infos


def render_hold_body(
    ax: Axes,
    hold_info: HoldRenderInfo,
    image_loader: Any,
) -> None:
    """渲染单个 Hold 的 Body 贴图（竖直拉伸矩形，D9）。

    拉伸方式:
    - 从 image_loader 获取纵向拉伸后的 Hold Body 贴图
    - 放置在 body_bottom_y 到 body_top_y 之间
    - X 方向居中对齐到该段的段内 X（hold_info.x_pixel）
    """
    if hold_info.body_height <= 0:
        return

    img = image_loader.get_hold_body_image(
        2, hold_info.note_info.is_multitap, int(round(hold_info.body_height))
    )
    img_w = img.shape[1]
    cx = hold_info.x_pixel  # 段内 X（跨栏尾段已映射到本栏坐标）
    extent = [
        cx - img_w / 2,
        cx + img_w / 2,
        hold_info.body_bottom_y,
        hold_info.body_top_y,
    ]
    ax.imshow(
        img,
        extent=extent,
        zorder=HOLD_BODY_ZORDER,
        interpolation="bilinear",
        clip_on=False,
    )


def render_hold_head_end(
    ax: Axes,
    hold_info: HoldRenderInfo,
    image_loader: Any,
    zorder: float | None = None,
) -> None:
    """渲染 Hold 的 Head 和 End 贴图。

    Head 放置在 startTime 位置；End 放置在 endTime 对应的 Y 位置。
    ★ End 与 Head/Body 保持同一 X（竖直对齐），不跟随轨迹终点偏移，
    以保证 Body 竖直矩形与两端贴图的观感一致（D9）。
    默认与普通 Note 同等 zorder 体系（按 startTime 统一排序后由调用方传入更精确）。
    """
    hl = hold_info.note_info.is_multitap
    z = zorder if zorder is not None else HOLD_HEAD_END_DEFAULT_ZORDER

    if hold_info.has_head:
        img = image_loader.get_note_image(2, hl)
        _place_centered(ax, img, hold_info.x_pixel, hold_info.head_y, z)

    if hold_info.has_end:
        img = image_loader.get_hold_end_image(hl)
        _place_centered(ax, img, hold_info.x_pixel, hold_info.end_y, z)


def render_hold_trajectory(
    ax: Axes,
    hold_info: HoldRenderInfo,
) -> None:
    """渲染 Hold 的轨迹曲线（浅灰色细线）。

    使用 matplotlib 的 plot 绘制采样点之间的连线。
    若轨迹点数 < 2（无移动或采样不足），则跳过。
    """
    points = hold_info.trajectory_points
    if not points or len(points) < 2:
        return

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    ax.plot(
        xs,
        ys,
        color=HOLD_TRAJECTORY_COLOR,
        linewidth=HOLD_TRAJECTORY_WIDTH,
        zorder=HOLD_TRAJECTORY_ZORDER,
        solid_capstyle="round",
        clip_on=False,
    )


def _place_centered(
    ax: Axes,
    img: np.ndarray,
    cx: float,
    cy: float,
    zorder: float,
) -> None:
    """将贴图中心对齐到 (cx, cy) 放置。

    clip_on=False: 栏底部（beat=栏起始拍）的 Head/End 贴图可越过主区
    底边界绘制在信息栏顶部边框之上，避免被边框遮挡。
    """
    img_h, img_w = img.shape[0], img.shape[1]
    extent = [
        cx - img_w / 2,
        cx + img_w / 2,
        cy - img_h / 2,
        cy + img_h / 2,
    ]
    ax.imshow(
        img,
        extent=extent,
        zorder=zorder,
        interpolation="bilinear",
        clip_on=False,
    )


__all__ = [
    "HoldRenderInfo",
    "prepare_hold_render_info",
    "render_hold_body",
    "render_hold_head_end",
    "render_hold_trajectory",
    "sample_hold_trajectory",
]
