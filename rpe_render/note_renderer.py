"""Note 贴图加载、多押判定与贴图放置。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from PIL import Image

from .constants import (
    HOLD_BODY_HL_IMAGE,
    HOLD_BODY_IMAGE,
    HOLD_END_HL_IMAGE,
    HOLD_END_IMAGE,
    NOTE_ICON_WIDTH,
    NOTE_IMAGE_MAP,
)
from .models import NoteData, NoteRenderInfo

logger = logging.getLogger("rpe_render")

# 贴图基础 zorder：按 startTime 从早到晚 10, 11, 12 ...
NOTE_BASE_ZORDER = 10


def note_zorder_key(info: NoteRenderInfo) -> tuple[float, int]:
    """Note 渲染顺序排序键（zorder 分配用）。

    同 beat 内 Hold 排前（zorder 更低、贴图先画），保证其他类型 Note
    不被 Hold 头遮挡（bug #1）；跨 beat 保持"晚的在上层"。
    """
    return (info.beat, 0 if info.note.type == 2 else 1)


class NoteImageLoader:
    """Note 贴图加载器。

    初始化时加载所有贴图到内存并预缩放，避免渲染过程中重复 I/O。
    缓存键: (kind, is_hl)，O(1) 查找。
    """

    def __init__(self, notes_dir: str | Path):
        """加载 notes_dir 下的所有 Note 贴图。

        Raises:
            FileNotFoundError: 若必要贴图缺失
        """
        self.notes_dir = Path(notes_dir)
        if not self.notes_dir.is_dir():
            raise FileNotFoundError(f"Notes directory not found: {self.notes_dir}")

        # 需要验证存在的全部 12 张贴图
        required: list[str] = []
        for normal, hl in NOTE_IMAGE_MAP.values():
            required.extend((normal, hl))
        required.extend(
            (
                HOLD_BODY_IMAGE,
                HOLD_BODY_HL_IMAGE,
                HOLD_END_IMAGE,
                HOLD_END_HL_IMAGE,
            )
        )

        for filename in required:
            path = self.notes_dir / filename
            if not path.is_file():
                raise FileNotFoundError(f"Required note image missing: {path}")

        # 缩放后的缓存: (filename) -> np.ndarray
        self._cache: dict[str, np.ndarray] = {}
        for filename in required:
            self._cache[filename] = self._load_scaled(filename)

        logger.info("Loaded %d note images from %s", len(required), self.notes_dir)

    def _load_scaled(self, filename: str) -> np.ndarray:
        """加载单张贴图并缩放到宽度 = NOTE_ICON_WIDTH（保持宽高比）。"""
        path = self.notes_dir / filename
        with Image.open(path) as img:
            img = img.convert("RGBA")
            w, h = img.size
            scale = NOTE_ICON_WIDTH / w
            target_h = max(1, round(h * scale))
            resized = img.resize((NOTE_ICON_WIDTH, target_h), Image.LANCZOS)
            return np.array(resized)

    def get_note_image(self, note_type: int, is_hl: bool) -> np.ndarray:
        """获取缩放后的 Note 贴图 RGBA 数组。

        Args:
            note_type: 1=Tap, 2=Hold(Head), 3=Flick, 4=Drag
            is_hl: 是否使用高亮（多押）版本
        """
        normal, hl = NOTE_IMAGE_MAP[note_type]
        filename = hl if is_hl else normal
        return self._cache[filename]

    def get_hold_body_image(self, note_type: int, is_hl: bool, target_height_px: int) -> np.ndarray:
        """获取 Hold Body 贴图，纵向拉伸到指定高度。

        Args:
            note_type: 固定为 2 (Hold)
            is_hl: 是否高亮
            target_height_px: 目标高度（像素），至少为 1
        """
        del note_type  # Hold 类型固定为 2，参数仅为与接口文档一致
        filename = HOLD_BODY_HL_IMAGE if is_hl else HOLD_BODY_IMAGE
        image = self._cache[filename]
        return stretch_vertical(image, max(1, int(target_height_px)))

    def get_hold_end_image(self, is_hl: bool) -> np.ndarray:
        """获取 HoldEnd 贴图。"""
        filename = HOLD_END_HL_IMAGE if is_hl else HOLD_END_IMAGE
        return self._cache[filename]


def stretch_vertical(image: np.ndarray, target_height: int) -> np.ndarray:
    """将 RGBA 数组纵向拉伸到指定高度（宽度保持 NOTE_ICON_WIDTH）。"""
    pil_img = Image.fromarray(image)
    stretched = pil_img.resize((NOTE_ICON_WIDTH, int(target_height)), Image.LANCZOS)
    return np.array(stretched)


def detect_multitap_groups(notes: list[NoteData]) -> set[int]:
    """检测多押组。

    使用原始 TimeT 分量比较（整数精确比较）：当多个 Note 的
    startTime [a, b, c] 三个分量完全相同时构成多押。

    Returns:
        属于多押组的所有 Note 的索引集合。
    """
    groups: dict[tuple, list[int]] = {}
    for i, note in enumerate(notes):
        if len(note.raw_start_time) == 3:
            key = ("timet", tuple(int(v) for v in note.raw_start_time))
        else:
            # 测试中手工构造的 NoteData 可能没有原始 TimeT，退化为精确浮点比较
            key = ("float", float(note.start_time_beat))
        groups.setdefault(key, []).append(i)

    multitap: set[int] = set()
    for indices in groups.values():
        if len(indices) >= 2:
            multitap.update(indices)
    return multitap


def detect_multitap_groups_at_beats(notes_info: list[NoteRenderInfo]) -> set[int]:
    """按映射后的主谱面时间判断实际同时出现的 Note。"""
    groups: dict[float, list[int]] = {}
    for index, info in enumerate(notes_info):
        # 映射只涉及简单倍乘；适度舍入避免分数拍浮点误差阻断多押。
        groups.setdefault(round(info.beat, 9), []).append(index)

    multitap: set[int] = set()
    for indices in groups.values():
        if len(indices) >= 2:
            multitap.update(indices)
    return multitap


def place_notes_on_axes(
    ax: Axes,
    notes_info: list[NoteRenderInfo],
    image_loader: Any,
) -> None:
    """在 Axes 上放置所有普通 Note 贴图（Tap/Flick/Drag；Hold Head 由 hold_renderer 处理）。

    Z 轴顺序: 按 startTime 从早到晚放置（同刻 Hold 排前），早的在下层（低 zorder），
    晚的在上层。zorder 枚举与 renderer.zorder_map 使用同一排序键（note_zorder_key），
    保证 Hold Head/End 与普通 Note 的层级一致。
    对齐方式: 贴图中心对齐到像素坐标。
    clip_on=False: 栏底部（beat=栏起始拍）的 Note 贴图可越过主区底边界
    绘制在信息栏顶部边框之上（主区 Axes zorder 高于信息栏），
    避免最下方 Note 的下半部分被边框遮挡。
    """
    sorted_notes = sorted(notes_info, key=note_zorder_key)
    for z_idx, info in enumerate(sorted_notes):
        if info.note.type == 2:
            continue  # Hold 由 hold_renderer 渲染 Head/Body/End

        img = image_loader.get_note_image(info.note.type, info.is_multitap)
        img_h, img_w = img.shape[0], img.shape[1]
        extent = [
            info.x_pixel - img_w / 2,  # left
            info.x_pixel + img_w / 2,  # right
            info.y_pixel - img_h / 2,  # bottom
            info.y_pixel + img_h / 2,  # top
        ]
        ax.imshow(
            img,
            extent=extent,
            zorder=NOTE_BASE_ZORDER + z_idx,
            # Note 贴图已经按目标像素尺寸缓存；nearest 避免 Matplotlib
            # 为数千个小图重复执行双线性重采样。
            interpolation="nearest",
            resample=False,
            clip_on=False,
        )
