"""曲绘背景处理：加载可选曲绘图片，应用高斯模糊、压暗后设为渲染背景。

背景采用 cover 模式：保持原图宽高比，等比缩放至完全覆盖画布后
居中裁剪多余部分，避免拉伸变形。

预览区半透明黑色覆盖层也在此实现：覆盖在曲绘之上、网格线之下。
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
from PIL import Image, ImageEnhance

from .constants import (
    BACKGROUND_BLUR_SIGMA,
    BACKGROUND_BRIGHTNESS,
    PREVIEW_BG_ALPHA,
    TRACK_BG_ALPHA,
)
from .models import ColumnInfo

logger = logging.getLogger("rpe_render")

BACKGROUND_ZORDER = -1

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
    pil_img = cover_crop(pil_img, target_w, target_h)
    if brightness != 1.0:
        pil_img = ImageEnhance.Brightness(pil_img).enhance(brightness)
    bg = np.array(pil_img)

    ax.imshow(
        bg,
        extent=[x_min, x_min + canvas_width_px, 0, canvas_height_px],
        aspect="auto",
        zorder=BACKGROUND_ZORDER,
        interpolation="bilinear",
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
