"""曲绘背景处理：加载可选曲绘图片，应用高斯模糊、压暗后设为渲染背景。

背景采用 cover 模式：保持原图宽高比，等比缩放至完全覆盖画布后
居中裁剪多余部分，避免拉伸变形。

预览区半透明黑色覆盖层也在此实现：覆盖在曲绘之上、网格线之下。
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
from PIL import Image, ImageEnhance

from .constants import (
    BACKGROUND_BLUR_SIGMA,
    BACKGROUND_BRIGHTNESS,
    BG_COLOR,
    JPEG_QUALITY,
    PREVIEW_BG_ALPHA,
    TRACK_BG_ALPHA,
)
from .models import ColumnInfo

logger = logging.getLogger("rpe_render")

BACKGROUND_ZORDER = -1

# Matplotlib 在绘制单张超大背景图时，会为整张图分配额外的 RGBA/NaN
# 临时数组。长谱面画布很容易达到上亿像素，改为小块贴图可将峰值内存
# 限制在单个 tile 大小，同时保持最终输出尺寸不变。
BACKGROUND_TILE_SIZE_PX = 1024
BACKGROUND_TILE_MAX_PIXELS = 8_000_000

# 覆盖层 zorder：位于曲绘背景（-1）之上、网格线（0）之下
PREVIEW_BG_ZORDER = -0.5

# 轨道加深层 zorder：位于预览区覆盖层（-0.5）之上、网格线（0）之下
TRACK_BG_ZORDER = -0.25


def load_and_blur_background(
    image_path: str | Path,
    blur_sigma: float = BACKGROUND_BLUR_SIGMA,
) -> np.ndarray | None:
    """加载曲绘图片并应用高斯模糊。

    Args:
        image_path: 曲绘图片路径
        blur_sigma: 高斯模糊 σ 值（默认 15.0）

    Returns:
        模糊后的 RGB numpy 数组 (H, W, 3)；若加载失败返回 None。
    """
    path = Path(image_path)
    if not path.is_file():
        logger.warning("Background image not found, skip background: %s", path)
        return None

    try:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
            blurred = rgb.filter(_gaussian_filter(blur_sigma))
            return np.array(blurred)
    except Exception:  # noqa: BLE001 - 图片损坏等任何加载失败都不应中断渲染
        logger.exception("Failed to load background image: %s", path)
        return None


def _gaussian_filter(sigma: float):  # noqa: ANN202 - 返回 PIL ImageFilter
    from PIL import ImageFilter

    return ImageFilter.GaussianBlur(radius=sigma)


def cover_crop(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """cover 模式缩放：保持宽高比填满目标尺寸后居中裁剪。

    Args:
        img: 原始 PIL 图片
        target_width: 目标宽度（px）
        target_height: 目标高度（px）

    Returns:
        尺寸恰为 (target_width, target_height) 的 PIL 图片
    """
    src_w, src_h = img.size
    scale = max(target_width / src_w, target_height / src_h)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_width) // 2
    top = (new_h - target_height) // 2
    return resized.crop((left, top, left + target_width, top + target_height))


def _iter_tile_boxes(
    width: int,
    height: int,
    tile_size: int = BACKGROUND_TILE_SIZE_PX,
) -> list[tuple[int, int, int, int]]:
    """Return bounded output tiles as ``(left, top, right, bottom)`` boxes."""
    width = max(1, int(width))
    height = max(1, int(height))
    tile_width = min(max(1, int(tile_size)), width)
    # Keep each intermediate RGBA/RGB tile small enough that a few workers can
    # coexist without recreating the whole high-DPI canvas in memory.
    tile_height = min(
        max(1, int(tile_size)),
        max(1, BACKGROUND_TILE_MAX_PIXELS // tile_width),
    )
    return [
        (left, top, min(left + tile_width, width), min(top + tile_height, height))
        for top in range(0, height, tile_height)
        for left in range(0, width, tile_width)
    ]


def _cover_tile(
    image: Image.Image,
    target_width: int,
    target_height: int,
    box: tuple[int, int, int, int],
) -> Image.Image:
    """Render one output tile directly from the source image.

    ``Image.transform(..., EXTENT, ...)`` applies the same cover mapping as
    ``cover_crop`` while allocating only the requested tile, so Pillow never
    has to create the enormous intermediate resized image.
    """
    src_w, src_h = image.size
    scale = max(target_width / src_w, target_height / src_h)
    scaled_w = max(1, round(src_w * scale))
    scaled_h = max(1, round(src_h * scale))
    crop_left = (scaled_w - target_width) // 2
    crop_top = (scaled_h - target_height) // 2
    left, top, right, bottom = box
    extent = (
        (crop_left + left) / scale,
        (crop_top + top) / scale,
        (crop_left + right) / scale,
        (crop_top + bottom) / scale,
    )
    return image.transform(
        (right - left, bottom - top),
        Image.Transform.EXTENT,
        extent,
        # EXTENT supports up to bicubic resampling (unlike resize, which also
        # supports LANCZOS). This still keeps the mapping smooth at tile edges
        # without allocating the full resized cover image.
        resample=Image.Resampling.BICUBIC,
    )


def _tile_worker_count(tile_count: int, requested: int | None = None) -> int:
    """Choose a bounded worker count; allow deployments to tune it by env."""
    cpu_count = max(1, os.cpu_count() or 1)
    if requested is None:
        try:
            render_workers = max(1, int(os.environ.get("RPE_RENDER_WORKERS", "1")))
        except ValueError:
            render_workers = 1
        default = max(1, min(8, cpu_count // render_workers))
        try:
            configured = int(os.environ.get("RPE_RENDER_TILE_WORKERS", default))
        except ValueError:
            configured = default
    else:
        configured = int(requested)
    return max(1, min(tile_count, configured))


def _compose_background_tile(
    image: Image.Image,
    foreground: Image.Image,
    target_width: int,
    target_height: int,
    box: tuple[int, int, int, int],
    brightness: float,
) -> tuple[tuple[int, int, int, int], Image.Image]:
    """Create one opaque-background RGBA tile over the foreground crop."""
    background = _cover_tile(image, target_width, target_height, box)
    if brightness != 1.0:
        background = ImageEnhance.Brightness(background).enhance(brightness)
    foreground_tile = foreground.crop(box)
    return box, Image.alpha_composite(background.convert("RGBA"), foreground_tile)


def _compose_background_in_tiles(
    foreground: Image.Image,
    bg_image: np.ndarray,
    brightness: float,
    tile_workers: int | None = None,
) -> None:
    """Composite a large background into ``foreground`` using parallel tiles."""
    target_width, target_height = foreground.size
    source = Image.fromarray(bg_image).convert("RGB")
    boxes = _iter_tile_boxes(target_width, target_height)
    workers = _tile_worker_count(len(boxes), tile_workers)

    # Pillow's resize/transform and alpha compositing release the GIL. Threads
    # therefore parallelize the C-level pixel work without copying a giant
    # foreground image between worker processes.
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bg-tile") as pool:
        batch_size = max(workers * 2, 1)
        for start in range(0, len(boxes), batch_size):
            futures = [
                pool.submit(
                    _compose_background_tile,
                    source,
                    foreground,
                    target_width,
                    target_height,
                    box,
                    brightness,
                )
                for box in boxes[start : start + batch_size]
            ]
            for future in futures:
                box, tile = future.result()
                foreground.paste(tile, box[:2])


def _imshow_cover_tiled(
    ax: Axes,
    image: Image.Image,
    target_width: int,
    target_height: int,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    region_top: int = 0,
    region_height: int | None = None,
    brightness: float = 1.0,
) -> None:
    """Display a region of a cover-cropped image without a giant array."""
    region_height = region_height or target_height
    region_bottom = region_top + region_height
    x_span = x_max - x_min
    y_span = y_max - y_min
    for full_box in _iter_tile_boxes(target_width, target_height):
        left, top, right, bottom = full_box
        clipped_top = max(top, region_top)
        clipped_bottom = min(bottom, region_bottom)
        if clipped_top >= clipped_bottom:
            continue
        tile = _cover_tile(image, target_width, target_height, (left, clipped_top, right, clipped_bottom))
        if brightness != 1.0:
            tile = ImageEnhance.Brightness(tile).enhance(brightness)
        local_top = clipped_top - region_top
        local_bottom = clipped_bottom - region_top
        tile_y_top = y_max - (local_top / region_height) * y_span
        tile_y_bottom = y_max - (local_bottom / region_height) * y_span
        tile_x_left = x_min + (left / target_width) * x_span
        tile_x_right = x_min + (right / target_width) * x_span
        ax.imshow(
            np.asarray(tile),
            extent=[tile_x_left, tile_x_right, tile_y_bottom, tile_y_top],
            aspect="auto",
            zorder=BACKGROUND_ZORDER,
            interpolation="nearest",
            resample=False,
        )


def apply_background_to_axes(
    ax: Axes,
    bg_image: np.ndarray,
    canvas_width_px: float,
    canvas_height_px: float,
    x_min: float = 0.0,
    brightness: float = BACKGROUND_BRIGHTNESS,
) -> None:
    """将模糊曲绘设置为 Axes 背景。

    处理流程：
        1. cover 模式缩放/居中裁剪到画布尺寸（保持宽高比不变形）
        2. 亮度压暗（默认系数 0.5），避免干扰前景内容
        3. 放置在最低 zorder 层

    Args:
        x_min: 背景在 Axes 中的左边界（用于覆盖画布两侧的标记边距区）
    """
    target_w = max(1, int(round(canvas_width_px)))
    target_h = max(1, int(round(canvas_height_px)))

    pil_img = Image.fromarray(bg_image).convert("RGB")
    if target_w * target_h <= BACKGROUND_TILE_MAX_PIXELS:
        pil_img = cover_crop(pil_img, target_w, target_h)
        if brightness != 1.0:
            pil_img = ImageEnhance.Brightness(pil_img).enhance(brightness)
        _imshow_tiled(
            ax,
            np.array(pil_img),
            x_min=x_min,
            x_max=x_min + canvas_width_px,
            y_min=0.0,
            y_max=canvas_height_px,
        )
    else:
        _imshow_cover_tiled(
            ax,
            pil_img,
            target_w,
            target_h,
            x_min=x_min,
            x_max=x_min + canvas_width_px,
            y_min=0.0,
            y_max=canvas_height_px,
            brightness=brightness,
        )


def apply_background_to_canvas(
    ax_main: Axes,
    ax_info: Axes,
    bg_image: np.ndarray,
    canvas_width_px: float,
    canvas_height_px: float,
    info_height_px: float,
    x_min: float = 0.0,
    brightness: float = BACKGROUND_BRIGHTNESS,
) -> None:
    """将模糊曲绘作为整图背景同时铺满主区与底部信息栏。

    曲绘先按"总画布（主区 + 信息栏高度之和）"cover 模式裁剪一次，
    再按区域切分：主区使用上部切片、信息栏使用下部切片。
    这样两区域的背景来自同一张连续图片（整图一致），而不是各自
    独立居中裁剪（否则信息栏会缩放/裁切出与主区无法衔接的画面）。

    Args:
        ax_main: 主时间轴 Axes（使用画布上部切片）
        ax_info: 底部信息栏 Axes（使用画布下部切片）
        bg_image: 模糊后的 RGB numpy 数组 (H, W, 3)
        canvas_width_px: 画布宽度（px，含两侧标记边距）
        canvas_height_px: 主区高度（px）
        info_height_px: 信息栏高度（px）
        x_min: 背景在 Axes 中的左边界（与 ax_main 的 xlim 左端一致）
        brightness: 亮度系数（1.0 为原始亮度），作用于整图一次
    """
    target_w = max(1, int(round(canvas_width_px)))
    main_h = max(1, int(round(canvas_height_px)))
    info_h = max(1, int(round(info_height_px)))

    pil_img = Image.fromarray(bg_image).convert("RGB")
    total_h = main_h + info_h
    if target_w * total_h <= BACKGROUND_TILE_MAX_PIXELS:
        # 一次 cover 裁剪到总画布（主区 + 信息栏），保证两区域背景连续
        pil_img = cover_crop(pil_img, target_w, total_h)
        if brightness != 1.0:
            pil_img = ImageEnhance.Brightness(pil_img).enhance(brightness)
        arr = np.array(pil_img)

        # 主区: 画布上部 main_h 行；信息栏: 画布底部 info_h 行。
        _imshow_tiled(
            ax_main,
            arr[:main_h],
            x_min=x_min,
            x_max=x_min + canvas_width_px,
            y_min=0.0,
            y_max=canvas_height_px,
        )
        _imshow_tiled(
            ax_info,
            arr[main_h:],
            x_min=x_min,
            x_max=x_min + canvas_width_px,
            y_min=0.0,
            y_max=info_height_px,
        )
    else:
        # 目标画布过大时直接从源图生成两块区域，避免 total_h 的巨型数组。
        _imshow_cover_tiled(
            ax_main,
            pil_img,
            target_w,
            total_h,
            x_min=x_min,
            x_max=x_min + canvas_width_px,
            y_min=0.0,
            y_max=canvas_height_px,
            region_top=0,
            region_height=main_h,
            brightness=brightness,
        )
        _imshow_cover_tiled(
            ax_info,
            pil_img,
            target_w,
            total_h,
            x_min=x_min,
            x_max=x_min + canvas_width_px,
            y_min=0.0,
            y_max=info_height_px,
            region_top=main_h,
            region_height=info_h,
            brightness=brightness,
        )


def save_rendered_image(
    foreground: Image.Image | bytes,
    output_path: str | Path,
    output_format: str,
    *,
    bg_image: np.ndarray | None = None,
    brightness: float = BACKGROUND_BRIGHTNESS,
    tile_workers: int | None = None,
) -> None:
    """用 Pillow 保存透明前景，并按需分块合成曲绘背景。

    主渲染路径不再让 Matplotlib 处理整幅背景图：Matplotlib 只绘制透明
    前景，随后 Pillow 负责 cover 裁剪和 alpha 合成。大画布按块并行处理，
    避免创建巨型缩放背景，也避免 Agg 在背景层申请额外临时数组。
    """
    if isinstance(foreground, Image.Image):
        foreground_image = foreground.convert("RGBA")
    else:
        with Image.open(BytesIO(foreground)) as fg_source:
            foreground_image = fg_source.convert("RGBA")

    if bg_image is not None:
        target_pixels = foreground_image.width * foreground_image.height
        if target_pixels <= BACKGROUND_TILE_MAX_PIXELS:
            background = Image.fromarray(bg_image).convert("RGB")
            background = cover_crop(background, *foreground_image.size)
            if brightness != 1.0:
                background = ImageEnhance.Brightness(background).enhance(brightness)
            result = Image.alpha_composite(background.convert("RGBA"), foreground_image)
        else:
            # Mutate the copied foreground in place, so the tiled path does not
            # hold another full-size RGBA result alongside the foreground.
            _compose_background_in_tiles(
                foreground_image,
                bg_image,
                brightness,
                tile_workers=tile_workers,
            )
            result = foreground_image
    else:
        result = foreground_image

    if output_format == "jpg":
        # JPEG 不支持 alpha；无曲绘时使用与原渲染路径一致的画布底色。
        if bg_image is None:
            flattened = Image.new("RGBA", result.size, BG_COLOR)
            flattened.alpha_composite(result)
            result = flattened
        result.convert("RGB").save(
            output_path,
            format="JPEG",
            quality=JPEG_QUALITY,
        )
    else:
        result.save(output_path, format="PNG")


def compose_background_and_save(
    foreground: Image.Image | bytes,
    bg_image: np.ndarray,
    output_path: str | Path,
    output_format: str,
    *,
    brightness: float = BACKGROUND_BRIGHTNESS,
    tile_workers: int | None = None,
) -> None:
    """兼容入口：将透明前景与背景合成并保存。"""
    save_rendered_image(
        foreground,
        output_path,
        output_format,
        bg_image=bg_image,
        brightness=brightness,
        tile_workers=tile_workers,
    )


def _imshow_tiled(
    ax: Axes,
    image: np.ndarray,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    tile_size: int = BACKGROUND_TILE_SIZE_PX,
) -> None:
    """将 RGB 图像拆成小块贴到 Axes，避免超大单图的临时内存峰值。

    ``imshow`` 默认 ``origin='upper'``，因此图像数组的顶部行对应数据坐标
    的 y_max；每个 tile 的 y 范围按此规则反向计算。
    """
    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        return
    tile_size = max(1, int(tile_size))
    # 长谱面的宽度通常远大于高度；优先整宽分块，只沿 Y 方向切片，
    # 将 AxesImage 数量从数百个降到十几个，同时让单块仍远小于整图。
    tile_width = width
    if width > BACKGROUND_TILE_MAX_PIXELS:
        tile_width = tile_size
    tile_height = min(tile_size, max(1, BACKGROUND_TILE_MAX_PIXELS // tile_width))
    x_span = x_max - x_min
    y_span = y_max - y_min

    for top in range(0, height, tile_height):
        bottom = min(top + tile_height, height)
        tile_y_top = y_max - (top / height) * y_span
        tile_y_bottom = y_max - (bottom / height) * y_span
        for left in range(0, width, tile_width):
            right = min(left + tile_width, width)
            tile_x_left = x_min + (left / width) * x_span
            tile_x_right = x_min + (right / width) * x_span
            ax.imshow(
                image[top:bottom, left:right],
                extent=[tile_x_left, tile_x_right, tile_y_bottom, tile_y_top],
                aspect="auto",
                zorder=BACKGROUND_ZORDER,
                interpolation="nearest",
                resample=False,
            )


def apply_preview_overlay(
    ax: Axes,
    canvas_width_px: float,
    canvas_height_px: float,
    alpha: float = PREVIEW_BG_ALPHA,
    x_min: float = 0.0,
) -> None:
    """在谱面预览区叠加半透明黑色底色。

    覆盖在曲绘背景之上、网格线之下，压暗预览区以突出白色标记文字
    与 Note 贴图。透明度 0.0 时不绘制任何内容。

    Args:
        alpha: 黑色透明度（0.0 ~ 1.0）
        x_min: 覆盖层在 Axes 中的左边界（与背景保持一致）
    """
    if alpha <= 0.0:
        return
    ax.add_patch(
        Rectangle(
            (x_min, 0.0),
            canvas_width_px,
            canvas_height_px,
            facecolor="black",
            alpha=min(alpha, 1.0),
            linewidth=0,
            edgecolor="none",
            zorder=PREVIEW_BG_ZORDER,
        )
    )


def apply_track_overlays(
    ax: Axes,
    columns: list[ColumnInfo],
    canvas_height_px: float,
    alpha: float = TRACK_BG_ALPHA,
) -> None:
    """为每条 Note 轨道（分栏竖直区域，不含轨道间隔栏）叠加加深底色。

    每栏一个黑色 Rectangle，只覆盖该栏的 Note 展示区域（pixel_left 到
    pixel_right），位于预览区覆盖层之上、网格线之下，使相邻轨道在视觉上
    更容易区分。透明度 0.0 时不绘制任何内容。

    Args:
        ax: 目标 Axes
        columns: 分栏信息列表
        canvas_height_px: 画布高度（px）
        alpha: 黑色透明度（0.0 ~ 1.0）
    """
    if alpha <= 0.0:
        return
    for col in columns:
        ax.add_patch(
            Rectangle(
                (col.pixel_left, 0.0),
                col.pixel_right - col.pixel_left,
                canvas_height_px,
                facecolor="black",
                alpha=min(alpha, 1.0),
                linewidth=0,
                edgecolor="none",
                zorder=TRACK_BG_ZORDER,
            )
        )
