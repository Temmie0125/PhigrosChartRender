"""Note 贴图加载、多押判定与贴图放置。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
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
    NOTE_BOMB_RENDER_LIMIT,
    NOTE_IMAGE_MAP,
)
from .models import NoteData, NoteRenderInfo

logger = logging.getLogger("rpe_render")

# 贴图基础 zorder：按 startTime 从早到晚 10, 11, 12 ...
NOTE_BASE_ZORDER = 10
NOTE_BATCH_THRESHOLD = 64
NOTE_BATCH_SPLIT_ZORDER = 20


@dataclass(frozen=True)
class SpritePlacement:
    """一个已确定像素位置与层级的 Note 贴图。"""

    image: np.ndarray
    center_x: float
    center_y: float
    zorder: float
    column: int


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


def _exact_render_signature(info: NoteRenderInfo) -> tuple:
    """Return a conservative signature for a safely deduplicable Note.

    The bomb defense must never use the fuzzy overlap threshold.  Non-Hold notes
    are fully determined by their exact mapped start beat, rendered X and type.
    A Hold also depends on its end and judge-line motion, so its source line,
    position and mapped end beat are included; differing geometry is therefore
    kept rather than accidentally hidden.
    """
    base = (info.beat, info.true_x, info.note.type)
    if info.note.type != 2:
        return base
    return base + (
        info.end_beat,
        info.note.position_x,
        info.line_index,
    )


def apply_note_bomb_defense(
    notes_info: list[NoteRenderInfo],
    limit: int = NOTE_BOMB_RENDER_LIMIT,
) -> set[int]:
    """Mark safely duplicated Notes that should not receive a sprite.

    Notes remain in ``notes_info`` so combo/count/overlap labels use the full
    chart.  Only exact duplicate groups are eligible.  A type with mixed
    geometry is kept intact because dropping any member could hide real chart
    content.  For safe duplicate groups, one member of every eligible type is
    selected first, then remaining slots are filled in original order.

    Returns the indices selected for actual rendering.
    """
    limit = max(1, int(limit))
    locations: dict[tuple[float, float], dict[int, list[list[int]]]] = {}
    signatures: dict[tuple[float, float, int, tuple], list[int]] = {}
    for index, info in enumerate(notes_info):
        info.render_enabled = True
        # Intentionally use exact float equality: unlike quantity markers,
        # this defense must not merge merely-nearby notes.
        location = (info.beat, info.true_x)
        signature = _exact_render_signature(info)
        signature_key = (location[0], location[1], info.note.type, signature)
        signatures.setdefault(signature_key, []).append(index)

    for (beat, x, note_type, signature), members in signatures.items():
        locations.setdefault((beat, x), {}).setdefault(note_type, []).append(members)

    selected: set[int] = set(range(len(notes_info)))
    for type_groups in locations.values():
        safe_groups: list[tuple[int, list[int]]] = []
        unsafe_indices: set[int] = set()
        for note_type, groups in type_groups.items():
            # A type is safe only when every Note at this location belongs to
            # one identical geometry group.  Mixed Hold paths are not pruned.
            flattened = [index for group in groups for index in group]
            if len(groups) == 1 and len(groups[0]) >= 2:
                safe_groups.append((note_type, groups[0]))
            else:
                unsafe_indices.update(flattened)
        if not safe_groups:
            continue

        keep: set[int] = set(unsafe_indices)
        remaining = max(0, limit - len(keep))
        # First pass guarantees one representative for each Note type.
        unsafe_types = {
            note_type for note_type, groups in type_groups.items()
            if any(index in unsafe_indices for group in groups for index in group)
        }
        ordered_groups = sorted(
            safe_groups,
            # If unsafe content already occupies slots, prefer types not yet
            # represented before falling back to source order.
            key=lambda item: (item[0] in unsafe_types, min(item[1])),
        )
        for _, members in ordered_groups:
            if remaining <= 0:
                break
            keep.add(members[0])
            remaining -= 1
        # Fill remaining capacity round-robin, preserving source order within
        # each type and avoiding a single type monopolising the quota.
        offsets = {note_type: 1 for note_type, _ in ordered_groups}
        while remaining > 0:
            added = False
            for note_type, members in ordered_groups:
                offset = offsets[note_type]
                if offset < len(members):
                    keep.add(members[offset])
                    offsets[note_type] = offset + 1
                    remaining -= 1
                    added = True
                    if remaining <= 0:
                        break
            if not added:
                break
        for _, members in safe_groups:
            for index in members:
                if index not in keep:
                    notes_info[index].render_enabled = False
                    selected.discard(index)
    return selected


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
        if not info.render_enabled:
            continue
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


def place_note_sprites_on_axes(
    ax: Axes,
    notes_info: list[NoteRenderInfo],
    hold_infos: list[Any],
    image_loader: Any,
    zorder_map: dict[int, float],
    *,
    batch_threshold: int = NOTE_BATCH_THRESHOLD,
) -> list[SpritePlacement]:
    """绘制低层级贴图，并返回可在最终 RGBA 缓冲区合批的贴图。

    少量贴图仍逐个交给 Matplotlib。大量贴图中，zorder <= 20 的元素
    必须保留为独立 artist，以维持它们与文字标记的层叠关系；其余元素
    均位于所有非贴图 artist 之上，可在 Agg 绘制完成后直接 alpha 合成。
    这种方式不会让 Matplotlib 对整栏透明大图执行昂贵的掩码和重采样。
    """
    placements: list[SpritePlacement] = []
    for info in notes_info:
        if not info.render_enabled:
            continue
        if info.note.type == 2:
            continue
        placements.append(
            SpritePlacement(
                image_loader.get_note_image(info.note.type, info.is_multitap),
                info.x_pixel,
                info.y_pixel,
                zorder_map[id(info)],
                info.column,
            )
        )

    for hold in hold_infos:
        zorder = zorder_map.get(id(hold.note_info), NOTE_BASE_ZORDER + 1)
        if hold.has_head:
            placements.append(
                SpritePlacement(
                    image_loader.get_note_image(2, hold.note_info.is_multitap),
                    hold.x_pixel,
                    hold.head_y,
                    zorder,
                    hold.column_index,
                )
            )
        if hold.has_end:
            placements.append(
                SpritePlacement(
                    image_loader.get_hold_end_image(hold.note_info.is_multitap),
                    hold.x_pixel,
                    hold.end_y,
                    zorder,
                    hold.column_index,
                )
            )

    if len(placements) < batch_threshold:
        for placement in placements:
            _place_sprite(ax, placement)
        return []

    deferred: list[SpritePlacement] = []
    for placement in placements:
        if placement.zorder <= NOTE_BATCH_SPLIT_ZORDER:
            _place_sprite(ax, placement)
        else:
            deferred.append(placement)
    return deferred


def _place_sprite(ax: Axes, placement: SpritePlacement) -> None:
    image = placement.image
    height, width = image.shape[:2]
    ax.imshow(
        image,
        extent=[
            placement.center_x - width / 2,
            placement.center_x + width / 2,
            placement.center_y - height / 2,
            placement.center_y + height / 2,
        ],
        zorder=placement.zorder,
        interpolation="nearest",
        resample=False,
        clip_on=False,
    )


def composite_note_sprites(
    foreground: Image.Image,
    ax: Axes,
    placements: list[SpritePlacement],
) -> None:
    """按 zorder 将延迟贴图直接合成到 Agg 生成的 RGBA 图像。"""
    if not placements:
        return

    canvas_height = foreground.height
    pil_cache: dict[tuple[int, int, int], Image.Image] = {}
    for placement in sorted(placements, key=lambda p: p.zorder):
        image = placement.image
        image_height, image_width = image.shape[:2]
        center_x, center_y = ax.transData.transform(
            (placement.center_x, placement.center_y)
        )
        left_px, bottom_px = ax.transData.transform(
            (placement.center_x - image_width / 2, placement.center_y - image_height / 2)
        )
        right_px, top_px = ax.transData.transform(
            (placement.center_x + image_width / 2, placement.center_y + image_height / 2)
        )
        target_width = max(1, round(abs(right_px - left_px)))
        target_height = max(1, round(abs(top_px - bottom_px)))
        cache_key = (id(image), target_width, target_height)
        sprite = pil_cache.get(cache_key)
        if sprite is None:
            sprite = Image.fromarray(image, mode="RGBA")
            if sprite.size != (target_width, target_height):
                sprite = sprite.resize(
                    (target_width, target_height), Image.Resampling.NEAREST
                )
            pil_cache[cache_key] = sprite
        left = round(center_x - target_width / 2)
        top = round(canvas_height - center_y - target_height / 2)
        foreground.alpha_composite(sprite, (left, top))
