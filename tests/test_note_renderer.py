"""note_renderer 单元测试（贴图加载 + 多押判定 + 贴图放置）。"""

import numpy as np
import pytest

from rpe_render import constants
from rpe_render.constants import NOTE_ICON_WIDTH
from rpe_render.models import NoteData, NoteRenderInfo
from rpe_render.note_renderer import (
    NoteImageLoader,
    apply_note_bomb_defense,
    detect_multitap_groups,
    note_zorder_key,
    place_notes_on_axes,
    composite_note_sprites,
    place_note_sprites_on_axes,
)


def make_note(
    note_type: int,
    beat: float,
    raw_start=None,
    idx: int = 0,
) -> NoteData:
    return NoteData(
        type=note_type,
        start_time_beat=beat,
        end_time_beat=beat,
        position_x=0.0,
        raw_start_time=raw_start if raw_start is not None else [int(beat), 0, 1],
    )


def make_info(note_type: int, beat: float) -> NoteRenderInfo:
    return NoteRenderInfo(
        note=make_note(note_type, beat),
        true_x=0.0,
        beat=beat,
        end_beat=beat,
        is_multitap=False,
        judge_line_name="L",
        column=int(beat // 64),
        x_pixel=0.0,
        y_pixel=0.0,
        y_pixel_end=0.0,
    )


class TestNoteZorderKey:
    def test_hold_before_others_same_beat(self):
        tap = make_info(1, 4.0)
        hold = make_info(2, 4.0)
        flick = make_info(3, 4.0)
        drag = make_info(4, 4.0)
        ordered = sorted([tap, flick, drag, hold], key=note_zorder_key)
        assert ordered[0] is hold  # 同刻 Hold 排前（zorder 更低）

    def test_later_beat_after_earlier(self):
        early = make_info(1, 4.0)
        late = make_info(2, 5.0)
        ordered = sorted([late, early], key=note_zorder_key)
        assert ordered == [early, late]

    def test_stable_within_hold_group(self):
        hold_a = make_info(2, 4.0)
        hold_b = make_info(2, 4.0)
        assert sorted([hold_b, hold_a], key=note_zorder_key) == [hold_a, hold_b]


class TestNoteImageLoader:
    def test_loads_all(self, notes_dir):
        loader = NoteImageLoader(notes_dir)
        # 4 种普通 + HL
        for t in (1, 2, 3, 4):
            assert loader.get_note_image(t, is_hl=False).shape[2] == 4
            assert loader.get_note_image(t, is_hl=True).shape[2] == 4
        # Hold body / end
        body = loader.get_hold_body_image(2, False, target_height_px=300)
        assert body.shape == (300, NOTE_ICON_WIDTH, 4)
        assert loader.get_hold_end_image(False).shape[1] == NOTE_ICON_WIDTH

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            NoteImageLoader(tmp_path / "nope")

    def test_missing_file_raises(self, tmp_path, notes_dir):
        import shutil

        target = tmp_path / "partial"
        shutil.copytree(notes_dir, target)
        (target / "Tap.png").unlink()
        with pytest.raises(FileNotFoundError, match="Tap.png"):
            NoteImageLoader(target)

    def test_scaling_width(self, notes_dir):
        loader = NoteImageLoader(notes_dir)
        img = loader.get_note_image(1, is_hl=False)
        assert img.shape[1] == NOTE_ICON_WIDTH
        assert img.shape[0] >= 1

    def test_normal_hl_same_render_size(self, notes_dir):
        # 回归：普通与 HL 是同一音符（仅差发光），渲染尺寸必须完全一致。
        # 之前按各自画布缩放导致 Tap 5px vs HL 10px，顶部形状被压平。
        loader = NoteImageLoader(notes_dir)
        for t in (1, 2, 3, 4):
            normal = loader.get_note_image(t, is_hl=False)
            highlight = loader.get_note_image(t, is_hl=True)
            assert normal.shape[1:] == highlight.shape[1:]
            assert normal.shape[1] == NOTE_ICON_WIDTH
        assert loader.get_hold_end_image(False).shape == loader.get_hold_end_image(
            True
        ).shape

    def test_glyph_center_preserved_after_padding(self, notes_dir):
        # 发光对称的贴图（Tap/Flick/Drag）补齐透明像素后中心仍重合；
        # Hold 头发光在下方、核心在贴图顶部，见 test_hold_head_top_aligned
        loader = NoteImageLoader(notes_dir)
        for t in (1, 3, 4):
            for is_hl in (False, True):
                arr = loader.get_note_image(t, is_hl)
                core = arr[:, :, 3] > 128
                rows = np.where(core.any(axis=1))[0]
                assert len(rows) > 0, f"type {t} hl={is_hl} has no visible core"
                glyph_center = (rows[0] + rows[-1]) / 2
                img_center = (arr.shape[0] - 1) / 2
                assert abs(glyph_center - img_center) <= 1.0, (
                    f"type {t} hl={is_hl}: glyph center {glyph_center} "
                    f"not at image center {img_center}"
                )

    @pytest.mark.skip(reason="贴图资源已按统一宽度重新制作，HoldHead 高度允许 HL 发光延伸")
    def test_hold_head_top_aligned(self, notes_dir):
        # 回归: Hold 头发光只在下方体现（核心在贴图顶部、发光向下延伸），
        # 普通版补齐时须与 HL 版同侧（顶部）对齐而非中心对齐，
        # 否则普通版核心相对判定线的位置与 HL 版不一致。
        loader = NoteImageLoader(notes_dir)
        normal = loader.get_note_image(2, is_hl=False)
        hl = loader.get_note_image(2, is_hl=True)
        assert normal.shape == hl.shape  # 渲染尺寸一致
        core_top = lambda a: np.where((a[:, :, 3] > 128).any(axis=1))[0][0]
        assert abs(core_top(normal) - core_top(hl)) <= 1.0, (
            f"HoldHead normal core top {core_top(normal)} != HL {core_top(hl)}"
        )
        # 核心上缘位于画布顶部附近（若中心对齐则约在画布一半处）
        assert core_top(normal) <= 1

    @pytest.mark.skip(reason="NOTE_PAIR_CANVAS_PADDING 已移除，贴图画布由资源本身控制")
    def test_padding_disabled_keeps_original_aspect(self, notes_dir, monkeypatch):
        monkeypatch.setattr(constants, "NOTE_PAIR_CANVAS_PADDING", False)
        loader = NoteImageLoader(notes_dir)
        tap = loader.get_note_image(1, is_hl=False)
        tap_hl = loader.get_note_image(1, is_hl=True)
        assert tap.shape[0] < tap_hl.shape[0]  # 不补齐时普通版明显更矮


class TestDetectMultitap:
    def test_same_timet_grouped(self):
        notes = [
            make_note(1, 1.25, raw_start=[1, 1, 4]),
            make_note(3, 1.25, raw_start=[1, 1, 4]),
            make_note(4, 2.0, raw_start=[2, 0, 1]),
        ]
        multitap = detect_multitap_groups(notes)
        assert multitap == {0, 1}

    def test_distinct_not_grouped(self):
        notes = [
            make_note(1, 1.0, raw_start=[1, 0, 1]),
            make_note(1, 1.25, raw_start=[1, 1, 4]),
        ]
        assert detect_multitap_groups(notes) == set()

    def test_numerically_equal_but_different_components(self):
        # [1,1,2] 与 [1,2,4] 数值相同但分量不同 → 非多押
        notes = [
            make_note(1, 1.5, raw_start=[1, 1, 2]),
            make_note(1, 1.5, raw_start=[1, 2, 4]),
        ]
        assert detect_multitap_groups(notes) == set()

    def test_triple_group(self):
        notes = [
            make_note(1, 3.0, raw_start=[3, 0, 1]),
            make_note(4, 3.0, raw_start=[3, 0, 1]),
            make_note(3, 3.0, raw_start=[3, 0, 1]),
            make_note(1, 4.0, raw_start=[4, 0, 1]),
        ]
        assert detect_multitap_groups(notes) == {0, 1, 2}


class TestNoteBombDefense:
    def test_caps_exact_duplicates_and_keeps_full_list(self):
        notes = [make_info(1, 4.0) for _ in range(10)]
        selected = apply_note_bomb_defense(notes)
        assert len(selected) == 4
        assert sum(note.render_enabled for note in notes) == 4

    def test_prioritizes_one_of_each_type(self):
        notes = [
            make_info(note_type, 4.0)
            for note_type in (1, 2, 3, 4)
            for _ in range(3)
        ]
        apply_note_bomb_defense(notes)
        rendered = [note.note.type for note in notes if note.render_enabled]
        assert len(rendered) == 4
        assert set(rendered) == {1, 2, 3, 4}

    def test_nearby_position_is_not_pruned_by_overlap_tolerance(self):
        first = make_info(1, 4.0)
        second = make_info(1, 4.0)
        # 50 is inside the quantity marker's default 75-unit tolerance, but
        # the bomb defense must still treat it as a distinct position.
        second.true_x = 50.0
        notes = [first, second]
        apply_note_bomb_defense(notes)
        assert all(note.render_enabled for note in notes)

    def test_different_hold_geometry_is_kept(self):
        first = make_info(2, 4.0)
        second = make_info(2, 4.0)
        first.end_beat = 8.0
        second.end_beat = 9.0
        notes = [first, second]
        apply_note_bomb_defense(notes)
        assert all(note.render_enabled for note in notes)


class TestPlaceNotesNotClippedAtBoundary:
    """栏底部（beat=栏起始拍）的 Note 贴图不应被主区底边界裁剪。

    贴图须关闭 clip，以便越过主区/信息栏交界绘制在边框之上，
    避免最下方 Note 的下半部分被边框遮挡。
    """

    def test_note_image_clip_disabled(self, notes_dir):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(-64, 386)
        ax.set_ylim(0, 64)

        loader = NoteImageLoader(notes_dir)
        info = make_info(1, 0.0)  # 栏起始拍（beat 0），位于主区底边界
        place_notes_on_axes(ax, [info], loader)

        assert len(ax.images) == 1
        assert ax.images[0].get_clip_on() is False
        plt.close(fig)


class TestNoteSpriteBatching:
    def test_large_sprite_set_is_batched_by_column(self, notes_dir):
        import matplotlib.pyplot as plt
        from PIL import Image

        from rpe_render.timeline import compute_columns

        fig = plt.figure(figsize=(4, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        columns = compute_columns(128.0)
        ax.set_xlim(-64, columns[-1].pixel_right + 64)
        ax.set_ylim(0, 4096)
        loader = NoteImageLoader(notes_dir)
        notes = [make_info(1, float(i)) for i in range(65)]
        for info in notes:
            info.column = min(int(info.beat // 64), 1)
            info.x_pixel = columns[info.column].pixel_left + 225
            info.y_pixel = (info.beat % 64) * 64
        zorders = {id(info): 10 + index for index, info in enumerate(notes)}

        deferred = place_note_sprites_on_axes(
            ax, notes, [], loader, zorders, batch_threshold=64
        )

        # zorder 10..20 保持独立，其余贴图延迟到最终 RGBA 缓冲区合成。
        assert len(ax.images) == 11
        assert len(deferred) == 54
        fig.canvas.draw()
        foreground = Image.frombuffer(
            "RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba(),
            "raw", "RGBA", 0, 1,
        ).copy()
        before = foreground.tobytes()
        composite_note_sprites(foreground, ax, deferred)
        assert foreground.tobytes() != before
        plt.close(fig)
