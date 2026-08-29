"""renderer 集成测试与 E2E 测试。"""

import matplotlib

matplotlib.use("Agg")

import pytest
from PIL import Image

from rpe_render.constants import (
    AFFECTED_AREA_MARGIN_LEFT_PX,
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    INFO_BAR_HEIGHT_PX,
    SIDE_MARKER_PADDING_PX,
)
from rpe_render.renderer import RenderConfig, render


class TestRenderIntegration:
    def test_column_beats_validation(self):
        assert RenderConfig(chart_path="x.json").smart_column_beats is True
        assert RenderConfig(chart_path="x.json", column_beats=16).column_beats == 16
        assert RenderConfig(chart_path="x.json", column_beats=128).column_beats == 128
        with pytest.raises(ValueError, match="column_beats"):
            RenderConfig(chart_path="x.json", column_beats=18)

    def test_jpeg_output(self, minimal_chart_path, notes_dir, tmp_path):
        out = tmp_path / "out.jpg"
        render(
            RenderConfig(
                chart_path=minimal_chart_path,
                output_path=out,
                notes_dir=notes_dir,
            )
        )

        image = Image.open(out)
        assert image.format == "JPEG"
        assert image.mode == "RGB"

    def test_minimal_chart_png(self, minimal_chart_path, notes_dir, tmp_path):
        out = tmp_path / "out.png"
        config = RenderConfig(
            chart_path=minimal_chart_path,
            output_path=out,
            notes_dir=notes_dir,
            smart_column_beats=False,
        )
        render(config)

        assert out.is_file()
        img = Image.open(out)
        w, h = img.size
        # 1 栏：宽 = 450 + 两侧标记边距，高 = 4096 + 信息栏（± savefig 取整误差）
        expected_w = 450 + 2 * SIDE_MARKER_PADDING_PX
        assert abs(w - expected_w) <= 2
        expected_h = COLUMN_BEATS * BEAT_HEIGHT_PX + INFO_BAR_HEIGHT_PX
        assert abs(h - expected_h) <= 4

    def test_smart_column_beats_changes_canvas_geometry(
        self, real_chart_path, notes_dir, tmp_path
    ):
        from math import ceil

        from rpe_render.constants import (
            BEAT_HEIGHT_PX,
            COLUMN_GAP,
            COLUMN_WIDTH,
            INFO_BAR_HEIGHT_PX,
            SIDE_MARKER_PADDING_PX,
        )
        from rpe_render.chart_parser import parse_chart
        from rpe_render.timeline import compute_max_beat, compute_smart_column_beats

        chart = parse_chart(real_chart_path)
        max_beat = compute_max_beat(chart)
        beats = compute_smart_column_beats(max_beat)
        out = tmp_path / "smart.png"
        render(
            RenderConfig(
                chart_path=real_chart_path,
                output_path=out,
                notes_dir=notes_dir,
                smart_column_beats=True,
            )
        )
        image = Image.open(out)
        expected_h = beats * BEAT_HEIGHT_PX + INFO_BAR_HEIGHT_PX
        assert abs(image.height - expected_h) <= 4
        # 受影响判定线可能让末栏额外增加区域间距，因此宽度至少包含基础分栏宽度。
        columns = int(ceil(max_beat / beats))
        base_w = columns * COLUMN_WIDTH + max(columns - 1, 0) * COLUMN_GAP + 2 * SIDE_MARKER_PADDING_PX
        assert image.width >= base_w - 3

    def test_transparent_without_background(self, minimal_chart_path, notes_dir, tmp_path):
        out = tmp_path / "transparent.png"
        render(
            RenderConfig(
                chart_path=minimal_chart_path,
                output_path=out,
                notes_dir=notes_dir,
            )
        )
        img = Image.open(out).convert("RGBA")
        alpha = img.getchannel("A")
        lo, hi = alpha.getextrema()
        assert lo < hi  # 存在透明区域

    def test_background_applied(self, minimal_chart_path, notes_dir, tmp_path):
        from PIL import Image as PILImage

        bg_path = tmp_path / "art.png"
        PILImage.new("RGB", (64, 64), color=(200, 30, 30)).save(bg_path)

        out_plain = tmp_path / "plain.png"
        out_bg = tmp_path / "withbg.png"
        render(
            RenderConfig(
                chart_path=minimal_chart_path, output_path=out_plain, notes_dir=notes_dir
            )
        )
        render(
            RenderConfig(
                chart_path=minimal_chart_path,
                output_path=out_bg,
                notes_dir=notes_dir,
                background_path=bg_path,
            )
        )

        a = __import__("numpy").array(PILImage.open(out_plain).convert("RGBA"))
        b = __import__("numpy").array(PILImage.open(out_bg).convert("RGBA"))
        # 有背景时大部分像素不透明且偏红
        assert (b[:, :, 3] > 200).mean() > 0.9
        assert (b[:, :, 0].astype(int) - b[:, :, 2]).mean() > 10

    def test_preview_bg_alpha_darkens_chart_area(
        self, minimal_chart_path, notes_dir, tmp_path
    ):
        from PIL import Image as PILImage

        bg_path = tmp_path / "art.png"
        PILImage.new("RGB", (64, 64), color=(200, 200, 200)).save(bg_path)

        out_light = tmp_path / "light.png"
        out_dark = tmp_path / "dark.png"
        render(
            RenderConfig(
                chart_path=minimal_chart_path,
                output_path=out_light,
                notes_dir=notes_dir,
                background_path=bg_path,
                preview_bg_alpha=0.0,
            )
        )
        render(
            RenderConfig(
                chart_path=minimal_chart_path,
                output_path=out_dark,
                notes_dir=notes_dir,
                background_path=bg_path,
                preview_bg_alpha=0.9,
            )
        )

        import numpy as np

        light = np.array(PILImage.open(out_light).convert("RGB"), dtype=float)
        dark = np.array(PILImage.open(out_dark).convert("RGB"), dtype=float)
        # 谱面预览区 = 顶部除去信息栏的部分；0.9 透明度应显著压暗
        chart_rows = slice(0, light.shape[0] - INFO_BAR_HEIGHT_PX)
        assert light[chart_rows].mean() - dark[chart_rows].mean() > 30

    def test_preview_bg_alpha_clamped(self):
        config = RenderConfig(chart_path="x.json", preview_bg_alpha=1.7)
        assert config.preview_bg_alpha == 1.0
        config = RenderConfig(chart_path="x.json", preview_bg_alpha=-0.3)
        assert config.preview_bg_alpha == 0.0

    def test_output_format_inferred_and_validated(self):
        assert RenderConfig(chart_path="x.json", output_path="x.jpg").output_format == "jpg"
        assert RenderConfig(
            chart_path="x.json", output_path="x.png", output_format="jpeg"
        ).output_format == "jpg"
        with pytest.raises(ValueError, match="Unsupported output format"):
            RenderConfig(chart_path="x.json", output_format="webp")

    def test_track_bg_alpha_darkens_note_area(self, minimal_chart_path, notes_dir, tmp_path):
        # 轨道区域（栏内）应显著暗于轨道间隔栏；预览区底色关闭以隔离本特性
        from PIL import Image as PILImage

        bg_path = tmp_path / "art.png"
        PILImage.new("RGB", (64, 64), color=(200, 200, 200)).save(bg_path)

        out = tmp_path / "track.png"
        render(
            RenderConfig(
                chart_path=minimal_chart_path,
                output_path=out,
                notes_dir=notes_dir,
                background_path=bg_path,
                preview_bg_alpha=0.0,
                track_bg_alpha=0.75,
            )
        )

        import numpy as np

        img = np.array(PILImage.open(out).convert("RGB"), dtype=float)
        # 谱面预览区 = 顶部除去信息栏的部分；栏内 x∈[100, 440]，间隔栏 x∈[520, 565]
        chart_rows = slice(0, img.shape[0] - INFO_BAR_HEIGHT_PX)
        track_mean = img[chart_rows, 100:440, :].mean()
        gap_mean = img[chart_rows, 520:565, :].mean()
        assert gap_mean - track_mean > 30

    def test_track_bg_alpha_clamped(self):
        config = RenderConfig(chart_path="x.json", track_bg_alpha=1.7)
        assert config.track_bg_alpha == 1.0
        config = RenderConfig(chart_path="x.json", track_bg_alpha=-0.3)
        assert config.track_bg_alpha == 0.0


class TestE2ERealChart:
    def test_real_chart_renders(self, real_chart_path, notes_dir, tmp_path):
        out = tmp_path / "real.png"
        render(
            RenderConfig(
                chart_path=real_chart_path,
                output_path=out,
                notes_dir=notes_dir,
            )
        )
        assert out.is_file()
        img = Image.open(out)
        assert img.size[0] > 0 and img.size[1] > 0

    def test_multitap_fixture(self, multitap_chart_path, notes_dir, tmp_path):
        out = tmp_path / "multitap.png"
        render(
            RenderConfig(
                chart_path=multitap_chart_path,
                output_path=out,
                notes_dir=notes_dir,
            )
        )
        assert out.is_file()

    def test_hold_cross_column_fixture(self, hold_cross_chart_path, notes_dir, tmp_path):
        out = tmp_path / "cross.png"
        render(
            RenderConfig(
                chart_path=hold_cross_chart_path,
                output_path=out,
                notes_dir=notes_dir,
            )
        )
        assert out.is_file()


class TestVerticalLineChartPhase3:
    """角度修正落点 / 重合判定 / 受影响段的集成语义测试（复刻 renderer Phase 3）。"""

    def test_angle_true_x_overlap_and_segments(self, vertical_line_chart_path):
        from math import ceil, cos, radians

        import numpy as np

        from rpe_render.affected_area_renderer import (
            affected_column_indices,
            build_affected_segments,
        )
        from rpe_render.chart_parser import parse_chart
        from rpe_render.easing.event_evaluator import (
            judge_line_rotate_at,
            judge_line_x_at,
        )
        from rpe_render.marker_renderer import compute_overlap_groups
        from rpe_render.models import NoteRenderInfo
        from rpe_render.timeline import compute_max_beat

        chart = parse_chart(vertical_line_chart_path)
        max_beat = compute_max_beat(chart)
        num_columns = max(1, int(ceil(max_beat / COLUMN_BEATS)))
        infos = []
        for line in chart.judge_line_list:
            for note in line.notes:
                t = note.start_time_beat
                angle = judge_line_rotate_at(line, t)
                true_x = judge_line_x_at(line, t) + note.position_x * cos(
                    radians(angle)
                )
                infos.append(
                    NoteRenderInfo(
                        note=note,
                        true_x=true_x,
                        beat=t,
                        end_beat=note.end_time_beat,
                        is_multitap=False,
                        judge_line_name=line.name,
                        column=min(int(t // COLUMN_BEATS), num_columns - 1),
                        x_pixel=0.0,
                        y_pixel=0.0,
                        y_pixel_end=0.0,
                        judge_line=line,
                        line_angle=angle,
                    )
                )

        by_line: dict[str, list] = {}
        for info in infos:
            by_line.setdefault(info.judge_line_name, []).append(info)

        # -180° 判定线：positionX=450 → 真实落点 -450（翻转）
        v180 = by_line["V180"][0]
        assert v180.true_x == pytest.approx(-450.0)

        # 90° 判定线：落点与 positionX 无关（cos90°=0）
        v90 = by_line["V90"]
        assert v90[0].true_x == pytest.approx(0.0)
        assert v90[1].true_x == pytest.approx(0.0)

        # 重合标注基于换算后的 true_x：两个 ±400 的 note 落点重合
        groups = compute_overlap_groups(infos)
        assert any(
            len(g) == 2 and all(n.judge_line_name == "V90" for n in g)
            for g in groups
        )

        # 受影响段：VNear 80° 全程一条跨栏段；V90 90° 一条段；V180 不受影响
        segs = build_affected_segments(infos)
        assert len(segs) == 2
        vnear_seg = [s for s in segs if s.notes[0].judge_line_name == "VNear"][0]
        assert vnear_seg.beat_start == 10.0
        assert vnear_seg.beat_end == 68.0
        assert affected_column_indices(segs) == {0, 1}


class TestE2EVerticalLineChart:
    def test_renders_boxes_areas_and_flipped_note(
        self, vertical_line_chart_path, notes_dir, tmp_path
    ):
        import numpy as np

        out = tmp_path / "vertical.png"
        render(
            RenderConfig(
                chart_path=vertical_line_chart_path,
                output_path=out,
                notes_dir=notes_dir,
                smart_column_beats=False,
            )
        )
        assert out.is_file()
        img = Image.open(out).convert("RGBA")
        w, h = img.size
        # 2 栏且两栏均受影响：小区域宽度 = 受影响 note 真实占用宽度，
        # 每栏额外间距 = MARGIN_LEFT + 占用宽度（见 compute_affected_area_widths）
        # 栏 0 positionX [-400,400] → 800/1350*450+54 = 320.67；栏 1 [-200,250] → 204
        expected_w = (
            2 * 450
            + 150
            + (AFFECTED_AREA_MARGIN_LEFT_PX + 320.67)
            + (AFFECTED_AREA_MARGIN_LEFT_PX + 204)
            + 2 * SIDE_MARKER_PADDING_PX
        )
        assert abs(w - expected_w) <= 3
        expected_h = COLUMN_BEATS * BEAT_HEIGHT_PX + INFO_BAR_HEIGHT_PX
        assert abs(h - expected_h) <= 4

        arr = np.array(img)

        # 主 Axes 的 xlim 左起 -SIDE_MARKER_PADDING_PX（数据 x = 图像 x - 64）；
        # Y 为栏内相对坐标：row = h - (信息栏高 + (beat % 64) * 每拍像素)
        def px(x_data: float, beat: float):
            row = h - int(
                INFO_BAR_HEIGHT_PX
                + (beat % COLUMN_BEATS) * BEAT_HEIGHT_PX
            )
            return arr[row, int(x_data + SIDE_MARKER_PADDING_PX)]

        # 受影响小区域与主栏轨道背景一致（同深度），比轨道间隙更深
        area = px(600, 13.0)
        track = px(100, 13.5)
        gap = px(450, 13.5)
        assert abs(int(area[3]) - int(track[3])) <= 20  # 与主栏轨道同深度
        assert int(gap[3]) + 50 < int(area[3])          # 深于间隙

        # 小区域仅与受影响区域等高：段范围之外（beat 5）无区域底色
        assert int(px(600, 5.0)[3]) + 50 < int(area[3])

        # 跨栏：栏 1 也有区域（VNear 66/68 拍），其外（beat 60）无区域
        # （栏 1 额外间距随区域宽度放大，区域左缘 = MARGIN_LEFT 之后，1500 在内）
        assert px(1500, 67.0)[3] > 200
        assert px(1500, 60.0)[3] < 200

        # 白框空心：内部为轨道底色，仅描边为白色
        interior = px(200, 12.5)
        assert interior[0] < 50  # 无白色填充
        r = h - int(INFO_BAR_HEIGHT_PX + 12.5 * BEAT_HEIGHT_PX)
        outline = arr[r, 236:242, 0].max()
        assert outline > 150  # 描边（白线）存在

        # -180° 判定线：落点翻转 → 图标在数据 x=75（+450 的位置 x=375 处只有网格线）
        assert px(75, 4.0)[1] > 150
        assert px(375, 4.0)[1] < 150
