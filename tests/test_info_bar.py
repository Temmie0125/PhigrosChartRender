"""info_bar 计算函数与渲染测试。"""

import matplotlib

matplotlib.use("Agg")
import pytest

from rpe_render.chart_parser import parse_chart
from rpe_render.info_bar import (
    beats_to_seconds,
    compute_bpm_range,
    compute_duration_seconds,
    compute_note_stats,
    format_bpm_text,
    format_duration,
    render_info_bar,
)
from rpe_render.models import NoteCountStats, NoteData


class TestComputeNoteStats:
    def test_counts(self):
        notes = [
            NoteData(1, 0, 0, 0),
            NoteData(1, 1, 1, 0),
            NoteData(2, 2, 5, 0),
            NoteData(3, 6, 6, 0),
            NoteData(4, 7, 7, 0),
            NoteData(4, 8, 8, 0),
        ]
        stats = compute_note_stats(notes)
        assert (stats.tap, stats.hold, stats.flick, stats.drag) == (2, 1, 1, 2)
        assert stats.total == 6


class TestDuration:
    def test_meta_duration_priority(self, minimal_chart_path):
        chart = parse_chart(minimal_chart_path)
        chart.meta.duration = 99.5
        assert compute_duration_seconds(chart) == pytest.approx(99.5)

    def test_bpm_integration(self, minimal_chart_path):
        # 120BPM 段 [0,32) 拍 + 180BPM 段；最大 endTime=8 拍 → 全在第一段
        chart = parse_chart(minimal_chart_path)
        chart.meta.duration = 0.0
        assert compute_duration_seconds(chart) == pytest.approx(8 * 60 / 120)

    def test_cross_bpm_change(self, minimal_chart_path):
        # 手工构造跨 BPM 段的拍数：120BPM 下 32 拍 = 16s，180BPM 下 4 拍 = 4/3s
        chart = parse_chart(minimal_chart_path)
        assert beats_to_seconds(chart, 36.0) == pytest.approx(16.0 + 4 / 3.0)

    def test_format(self):
        assert format_duration(0) == "0:00"
        assert format_duration(154) == "2:34"
        assert format_duration(60.4) == "1:00"


class TestComputeBpmRange:
    def test_min_max(self, minimal_chart_path):
        chart = parse_chart(minimal_chart_path)
        assert compute_bpm_range(chart) == (120.0, 180.0)

    def test_empty_chart(self, minimal_chart_path):
        chart = parse_chart(minimal_chart_path)
        chart.bpm_list = []
        assert compute_bpm_range(chart) == (0.0, 0.0)


class TestFormatBpmText:
    def test_single_bpm_no_range(self):
        # 定速曲目: 只写精确值，不写范围
        assert format_bpm_text(120.0, 120.0) == "BPM：120"

    def test_range_when_bpm_changes(self):
        assert format_bpm_text(100.0, 200.0) == "BPM：100~200"

    def test_single_bpm_rendered_without_tilde(self, minimal_chart_path):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(10, 10), dpi=100)
        ax_info = fig.add_axes([0, 0, 1, 0.2])
        chart = parse_chart(minimal_chart_path)
        chart.bpm_list = [chart.bpm_list[0]]  # 只保留第一个 BPM（定速）
        render_info_bar(
            ax_info,
            chart,
            NoteCountStats(),
            total_duration_seconds=10.0,
            canvas_width_px=450,
        )
        joined = "\n".join(t.get_text() for t in ax_info.texts)
        assert "BPM：120" in joined
        assert "~" not in joined
        plt.close(fig)


class TestRenderInfoBar:
    def test_texts_present(self, minimal_chart_path):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(10, 10), dpi=100)
        ax_info = fig.add_axes([0, 0, 1, 0.2])
        chart = parse_chart(minimal_chart_path)
        stats = NoteCountStats(tap=3, hold=2, flick=1, drag=4)
        render_info_bar(
            ax_info,
            chart,
            stats,
            total_duration_seconds=154.0,
            canvas_width_px=450,
        )
        texts = [t.get_text() for t in ax_info.texts]
        joined = "\n".join(texts)
        assert "Minimal Test" in joined
        assert "2:34" in joined
        assert "IN 13" in joined
        assert "Tap: 3" in joined
        # 标题与 BPM 范围（最低~最高）
        assert "Basic Information" in joined
        assert "Notes Info" in joined
        assert "BPM：120~180" in joined
        assert "Combo: 10" in joined
        plt.close(fig)

    def test_double_border_patches(self, minimal_chart_path):
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch, Rectangle
        from matplotlib.colors import to_hex

        from rpe_render.constants import (
            INFO_BAR_BORDER_COLOR,
            INFO_BAR_BORDER_GAP_PX,
            INFO_BAR_BORDER_WIDTH_PX,
            INFO_BAR_OUTER_BORDER_ALPHA,
            PREVIEW_BG_ALPHA,
        )

        fig = plt.figure(figsize=(10, 10), dpi=100)
        ax_info = fig.add_axes([0, 0, 1, 0.2])
        chart = parse_chart(minimal_chart_path)
        render_info_bar(
            ax_info,
            chart,
            NoteCountStats(),
            total_duration_seconds=10.0,
            canvas_width_px=450,
        )

        # 最外层: 透明度 0.75 的深灰色方框
        rects = [p for p in ax_info.patches if isinstance(p, Rectangle)]
        assert len(rects) == 1
        outer = rects[0]
        assert outer.get_alpha() == INFO_BAR_OUTER_BORDER_ALPHA
        assert to_hex(outer.get_edgecolor()) == INFO_BAR_BORDER_COLOR.lower()
        assert outer.get_zorder() == 2

        # 内层: 内部填充 + 圆角边框（zorder 1 与 3）
        boxes = [p for p in ax_info.patches if isinstance(p, FancyBboxPatch)]
        assert len(boxes) == 2
        fill, inner = sorted(boxes, key=lambda p: p.get_zorder())
        # 内部填充 = 配置区（非轨道部分）同款底色（黑色覆盖层）
        assert fill.get_facecolor() == (0.0, 0.0, 0.0, PREVIEW_BG_ALPHA)
        assert fill.get_zorder() == 1
        # 内层圆角边框: 3px 不透明深灰色
        assert inner.get_linewidth() == INFO_BAR_BORDER_WIDTH_PX
        assert inner.get_alpha() is None  # 未指定透明度 = 不透明
        assert to_hex(inner.get_edgecolor()) == INFO_BAR_BORDER_COLOR.lower()
        assert inner.get_zorder() == 3
        # 与外框间隔约 8px（两框描边中线相距 3/2 + 8 + 3/2 = 11）
        assert inner.get_x() - outer.get_x() == pytest.approx(
            INFO_BAR_BORDER_WIDTH_PX / 2
            + INFO_BAR_BORDER_WIDTH_PX
            + INFO_BAR_BORDER_GAP_PX
        )
        plt.close(fig)

    def test_note_stat_colors(self, minimal_chart_path):
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_hex

        from rpe_render.constants import (
            INFO_BAR_TEXT_COLOR,
            NOTE_COLOR_DRAG,
            NOTE_COLOR_FLICK,
            NOTE_COLOR_HOLD,
            NOTE_COLOR_TAP,
        )

        fig = plt.figure(figsize=(10, 10), dpi=100)
        ax_info = fig.add_axes([0, 0, 1, 0.2])
        chart = parse_chart(minimal_chart_path)
        render_info_bar(
            ax_info,
            chart,
            NoteCountStats(tap=1, hold=2, flick=3, drag=4),
            total_duration_seconds=10.0,
            canvas_width_px=450,
        )
        color_by_text = {t.get_text(): t.get_color() for t in ax_info.texts}
        assert to_hex(color_by_text["Tap: 1"]) == NOTE_COLOR_TAP.lower()
        assert to_hex(color_by_text["Drag: 4"]) == NOTE_COLOR_DRAG.lower()
        assert to_hex(color_by_text["Hold: 2"]) == NOTE_COLOR_HOLD.lower()
        assert to_hex(color_by_text["Flick: 3"]) == NOTE_COLOR_FLICK.lower()
        # Combo 总数保持白色
        assert to_hex(color_by_text["Combo: 10"]) == INFO_BAR_TEXT_COLOR.lower()
        plt.close(fig)

    def test_titles_colored_with_shadow(self, minimal_chart_path):
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_hex

        from rpe_render.constants import INFO_BAR_TITLE_COLOR

        fig = plt.figure(figsize=(10, 10), dpi=100)
        ax_info = fig.add_axes([0, 0, 1, 0.2])
        chart = parse_chart(minimal_chart_path)
        render_info_bar(
            ax_info,
            chart,
            NoteCountStats(),
            total_duration_seconds=10.0,
            canvas_width_px=450,
        )
        titles = [t for t in ax_info.texts if t.get_text() == "Basic Information"]
        assert len(titles) == 2  # 阴影副本 + 主标题
        main = [t for t in titles if t.get_zorder() == 5][0]
        shadow = [t for t in titles if t.get_zorder() == 4][0]
        assert to_hex(main.get_color()) == INFO_BAR_TITLE_COLOR.lower()
        assert main.get_position()[1] - shadow.get_position()[1] == pytest.approx(1.0)
        assert shadow.get_alpha() == 0.5
        plt.close(fig)
