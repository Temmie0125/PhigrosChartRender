"""background 模块单元测试。"""

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pytest
from PIL import Image

from rpe_render.background import (
    apply_background_to_axes,
    apply_background_to_canvas,
    apply_preview_overlay,
    apply_track_overlays,
    cover_crop,
    load_and_blur_background,
)
from rpe_render.constants import TRACK_BG_ALPHA
from rpe_render.models import ColumnInfo


def make_columns() -> list[ColumnInfo]:
    """两个分栏：栏 1 占 0..450，栏 2 占 600..1050（间隔 150）。"""
    return [
        ColumnInfo(
            index=0,
            beat_start=0.0,
            beat_end=64.0,
            pixel_left=0.0,
            pixel_right=450.0,
            pixel_bottom=0.0,
            pixel_top=100.0,
        ),
        ColumnInfo(
            index=1,
            beat_start=64.0,
            beat_end=128.0,
            pixel_left=600.0,
            pixel_right=1050.0,
            pixel_bottom=0.0,
            pixel_top=100.0,
        ),
    ]


def gradient_image(w: int, h: int) -> Image.Image:
    """水平渐变图：像素值随 x 线性变化，用于检测裁剪窗口位置。"""
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    step = 255 / max(1, w - 1)
    arr[:, :, 0] = (np.arange(w) * step).astype(np.uint8)[None, :]
    arr[:, :, 1] = arr[:, :, 0]
    arr[:, :, 2] = arr[:, :, 0]
    return Image.fromarray(arr)


class TestLoadAndBlur:
    def test_load(self, tmp_path):
        p = tmp_path / "art.png"
        Image.new("RGB", (64, 64), color=(120, 120, 120)).save(p)
        bg = load_and_blur_background(p)
        assert bg is not None
        assert bg.shape[2] == 3

    def test_not_found_returns_none(self, tmp_path):
        assert load_and_blur_background(tmp_path / "nope.png") is None

    def test_blur_applied(self, tmp_path):
        # 高对比棋盘图模糊后应趋于中间灰
        p = tmp_path / "sharp.png"
        arr = np.full((64, 64, 3), 255, dtype=np.uint8)
        arr[::2, ::2] = 0
        Image.fromarray(arr).save(p)
        bg = load_and_blur_background(p)
        assert bg is not None
        center = bg[16:48, 16:48]
        mean = center.mean()
        assert 30 < mean < 225  # 已不是原始的纯黑/纯白


class TestCoverCrop:
    def test_output_size_exact(self):
        img = Image.new("RGB", (800, 400))
        out = cover_crop(img, 300, 600)
        assert out.size == (300, 600)

    def test_aspect_preserved_no_stretch(self):
        # 2:1 源图 → 1:2 目标：按高缩放（scale=3）→ 2400x1200 → 居中裁 600 宽
        # 渐变图可验证裁剪窗口位置，确认未发生横向压缩
        src = gradient_image(800, 400)
        target_w, target_h = 600, 1200
        out = np.array(cover_crop(src, target_w, target_h))
        assert out.shape[:2] == (target_h, target_w)

        # scale = max(600/800, 1200/400) = 3；缩放后宽 2400，left=(2400-600)//2=900
        # 原图 x=300 处的灰度值应出现在输出最左列
        expected_left_val = 255 * 300 / 799
        actual_left_val = out[:, 0, 0].mean()  # 最左列（通道 0）
        assert actual_left_val == pytest.approx(expected_left_val, abs=6.0)

    def test_upscale_small_source(self):
        img = Image.new("RGB", (50, 50), color=(10, 20, 30))
        out = cover_crop(img, 450, 6144)
        assert out.size == (450, 6144)
        arr = np.array(out)
        assert abs(int(arr[:, :, 2].mean()) - 30) <= 3


class TestApplyBackground:
    def test_large_canvas_is_split_into_tiles(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 2400)
        ax.set_ylim(0, 1800)
        bg = np.full((32, 32, 3), 200, dtype=np.uint8)
        apply_background_to_axes(ax, bg, canvas_width_px=2400, canvas_height_px=1800)

        # 大画布不能退化成单个覆盖全画布的 AxesImage，否则 Matplotlib
        # 绘制时会申请与整张输出同等大小的临时 RGBA 数组。
        assert len(ax.get_images()) > 1
        fig.canvas.draw()
        plt.close(fig)

    def test_dimmed_to_half(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)

        bg = np.full((100, 100, 3), 200, dtype=np.uint8)
        apply_background_to_axes(ax, bg, canvas_width_px=100, canvas_height_px=100)

        fig.canvas.draw()
        rendered = np.asarray(fig.canvas.buffer_rgba())
        mean_brightness = rendered[:, :, :3].mean()

        # 200 * 0.75 = 150 左右（远低于未压暗的 200）
        assert mean_brightness < 175
        plt.close(fig)

    def test_zorder_below_content(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        bg = np.full((10, 10, 3), 255, dtype=np.uint8)
        apply_background_to_axes(ax, bg, 100.0, 100.0)
        images = ax.get_images()
        assert len(images) == 1
        assert images[0].get_zorder() == -1
        plt.close(fig)

    def test_extent_offsets_with_x_min(self):
        # 画布两侧标记边距区需要背景覆盖：extent 左边界应等于 x_min
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(-50, 150)
        ax.set_ylim(0, 100)
        bg = np.full((10, 10, 3), 128, dtype=np.uint8)
        apply_background_to_axes(ax, bg, 200.0, 100.0, x_min=-50.0)
        extent = ax.get_images()[0].get_extent()
        assert extent[0] == -50.0
        assert extent[1] == 150.0
        assert extent[2] == 0.0
        assert extent[3] == 100.0
        plt.close(fig)


class TestApplyBackgroundToCanvas:
    """整图背景：主区 + 信息栏共用一次 cover 裁剪的上下切片。"""

    def test_splits_single_crop_across_axes(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax_main = fig.add_axes([0, 0.2, 1, 0.8])
        ax_info = fig.add_axes([0, 0, 1, 0.2])
        ax_main.set_xlim(-64, 386)
        ax_main.set_ylim(0, 100)
        ax_info.set_xlim(-64, 386)
        ax_info.set_ylim(0, 50)

        bg = np.full((80, 80, 3), 128, dtype=np.uint8)
        apply_background_to_canvas(
            ax_main,
            ax_info,
            bg,
            canvas_width_px=450.0,
            canvas_height_px=100.0,
            info_height_px=50.0,
            x_min=-64.0,
        )
        main_img = ax_main.get_images()[0]
        info_img = ax_info.get_images()[0]
        # 高度切片: 主区 100 行 + 信息栏 50 行 = 一次 cover 裁剪的总高
        assert np.asarray(main_img.get_array()).shape[0] == 100
        assert np.asarray(info_img.get_array()).shape[0] == 50
        # 亮度随配置压暗（默认 0.75）
        assert np.asarray(main_img.get_array()).mean() == pytest.approx(128 * 0.75, abs=1)
        # 两区域 extent 左右一致、上下各自对应本区域高度（整图连续）
        assert list(main_img.get_extent()) == [-64.0, 386.0, 0.0, 100.0]
        assert list(info_img.get_extent()) == [-64.0, 386.0, 0.0, 50.0]
        plt.close(fig)

    def test_no_brightness_keeps_pixels(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax_main = fig.add_axes([0, 0.2, 1, 0.8])
        ax_info = fig.add_axes([0, 0, 1, 0.2])
        ax_main.set_xlim(-64, 386)
        ax_main.set_ylim(0, 100)
        ax_info.set_xlim(-64, 386)
        ax_info.set_ylim(0, 50)

        bg = np.full((80, 80, 3), 128, dtype=np.uint8)
        apply_background_to_canvas(
            ax_main,
            ax_info,
            bg,
            canvas_width_px=450.0,
            canvas_height_px=100.0,
            info_height_px=50.0,
            x_min=-64.0,
            brightness=1.0,
        )
        assert np.asarray(ax_info.get_images()[0].get_array()).mean() == pytest.approx(
            128, abs=1
        )
        plt.close(fig)


class TestPreviewOverlay:
    def test_overlay_patch_properties(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(-64, 514)
        ax.set_ylim(0, 100)
        apply_preview_overlay(ax, 578.0, 100.0, alpha=0.4, x_min=-64.0)
        assert len(ax.patches) == 1
        patch = ax.patches[0]
        assert patch.get_facecolor() == (0.0, 0.0, 0.0, 0.4)
        assert patch.get_zorder() == -0.5  # 背景之上、网格（0）之下
        assert patch.get_width() == pytest.approx(578.0)
        assert patch.get_height() == pytest.approx(100.0)
        plt.close(fig)

    def test_overlay_skipped_when_alpha_zero(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        apply_preview_overlay(ax, 100.0, 100.0, alpha=0.0)
        assert len(ax.patches) == 0
        plt.close(fig)

    def test_overlay_darkens_background(self):
        # 黑覆盖层叠在亮背景上应显著降低像素亮度
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        bg = np.full((100, 100, 3), 200, dtype=np.uint8)
        apply_background_to_axes(ax, bg, canvas_width_px=100, canvas_height_px=100)
        apply_preview_overlay(ax, 100.0, 100.0, alpha=0.5)
        fig.canvas.draw()
        rendered = np.asarray(fig.canvas.buffer_rgba())
        mean_brightness = rendered[:, :, :3].mean()
        # 200 * 0.5（压暗）* (1 - 0.5)（覆盖层）= 50 附近
        assert mean_brightness < 90
        plt.close(fig)


class TestTrackOverlays:
    """每条 Note 轨道（栏内竖直区域）的额外加深覆盖层。"""

    def test_one_rectangle_per_column(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(-64, 1114)
        ax.set_ylim(0, 100)
        apply_track_overlays(ax, make_columns(), canvas_height_px=100.0, alpha=0.75)
        assert len(ax.patches) == 2
        p = ax.patches[0]
        assert p.get_facecolor() == (0.0, 0.0, 0.0, 0.75)
        assert p.get_zorder() == -0.25  # 预览区覆盖层（-0.5）之上、网格（0）之下
        assert p.get_width() == pytest.approx(450.0)
        assert p.get_height() == pytest.approx(100.0)
        # 第二栏独立覆盖，只覆盖栏内区域（不含轨道间隔栏）
        assert ax.patches[1].get_x() == pytest.approx(600.0)
        plt.close(fig)

    def test_skipped_when_alpha_zero(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        apply_track_overlays(ax, make_columns(), 100.0, alpha=0.0)
        assert len(ax.patches) == 0
        plt.close(fig)

    def test_darkens_track_area_only(self):
        # 亮背景上：栏内区域显著暗于轨道间隔栏（覆盖层只作用于栏内）
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(4, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 1050)
        ax.set_ylim(0, 100)
        bg = np.full((100, 100, 3), 200, dtype=np.uint8)
        apply_background_to_axes(ax, bg, canvas_width_px=1050.0, canvas_height_px=100.0)
        apply_track_overlays(ax, make_columns(), 100.0, alpha=0.75)
        fig.canvas.draw()
        rendered = np.asarray(fig.canvas.buffer_rgba())
        gray = rendered[:, :, :3].mean(axis=2)
        # 400px 画布 ↔ 数据宽度 1050：栏 1 (0..450) → px 0..171，间隔 (450..600) → px 171..228
        track_mean = gray[:, 30:160].mean()   # 栏 1 内部
        gap_mean = gray[:, 185:220].mean()    # 栏 1 与栏 2 之间的间隔
        assert track_mean < gap_mean - 50
        plt.close(fig)

    def test_default_alpha_from_constants(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(2, 2), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        apply_track_overlays(ax, make_columns(), 100.0)
        assert ax.patches[0].get_facecolor()[3] == TRACK_BG_ALPHA
        plt.close(fig)
