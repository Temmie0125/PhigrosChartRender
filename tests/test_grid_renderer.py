"""grid_renderer 集成测试：检查 Axes 上的 Line2D / Text 状态。"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from rpe_render.constants import (
    BAR_LINE_COLOR,
    BEAT_HEIGHT_PX,
    BEAT_LINE_COLOR,
    COLUMN_BEATS,
    MARKER_MARGIN_PX,
)
from rpe_render.grid_renderer import render_grid, render_single_column_grid
from rpe_render.marker_renderer import render_markers, render_overlap_markers
from rpe_render.models import BPMEvent, ColumnInfo, NoteData, NoteRenderInfo


def make_column(index: int = 0) -> ColumnInfo:
    left = index * 600.0
    return ColumnInfo(
        index=index,
        beat_start=index * COLUMN_BEATS,
        beat_end=(index + 1) * COLUMN_BEATS,
        pixel_left=left,
        pixel_right=left + 450.0,
        pixel_bottom=0.0,
        pixel_top=COLUMN_BEATS * BEAT_HEIGHT_PX,
    )


@pytest.fixture()
def ax():
    fig = plt.figure(figsize=(4, 8), dpi=100)
    axes = fig.add_axes([0, 0, 1, 1])
    yield axes
    plt.close(fig)


class TestSingleColumnGrid:
    def test_line_counts(self, ax):
        col = make_column()
        render_single_column_grid(ax, col, [], is_first_column=True)
        # 每拍一条线：64 拍 → 65 条（含首尾）
        lines = [l for l in ax.get_lines()]
        assert len(lines) == COLUMN_BEATS + 1

    def test_beat_number_labels(self, ax):
        col = make_column()
        render_single_column_grid(ax, col, [], is_first_column=True)
        texts = [t.get_text() for t in ax.texts]
        for beat in range(0, COLUMN_BEATS + 1, 4):
            assert str(beat) in texts

    def test_labels_left_side_only(self, ax):
        """拍号标记统一绘制在栏左侧。"""
        col = make_column()
        render_single_column_grid(ax, col, [], is_first_column=True)
        for t in ax.texts:
            x = t.get_position()[0]
            assert x < col.pixel_left, f"text '{t.get_text()}' at x={x} is not left of column"

    def test_labels_left_of_second_column(self, ax):
        col = make_column(1)
        render_single_column_grid(ax, col, [], is_first_column=False)
        xs = {round(t.get_position()[0]) for t in ax.texts}
        # 全部位于 pixel_left - margin 处，无右侧标记
        assert xs == {round(col.pixel_left - MARKER_MARGIN_PX)}

    def test_bpm_marker(self, ax):
        bpm_list = [BPMEvent(bpm=174.0, start_time=[16, 0, 1])]
        col = make_column()
        render_single_column_grid(ax, col, bpm_list, is_first_column=True)
        joined = "\n".join(t.get_text() for t in ax.texts)
        assert "BPM:174" in joined

    def test_bpm_marker_other_column_not_shown(self, ax):
        bpm_list = [BPMEvent(bpm=174.0, start_time=[80, 0, 1])]
        col = make_column(0)
        render_single_column_grid(ax, col, bpm_list, is_first_column=True)
        joined = "\n".join(t.get_text() for t in ax.texts)
        assert "BPM" not in joined


class TestRenderGrid:
    def test_all_columns(self, ax):
        cols = [make_column(0), make_column(1)]
        render_grid(ax, cols, [])
        assert len(ax.get_lines()) == 2 * (COLUMN_BEATS + 1)

    def test_line_colors_are_gray(self, ax):
        # 拍线/小节线均为灰色（不再是黑色），拍 0 同时是两种线的分界
        col = make_column()
        render_single_column_grid(ax, col, [], is_first_column=True)
        colors = {l.get_color() for l in ax.get_lines()}
        assert colors == {BEAT_LINE_COLOR, BAR_LINE_COLOR}


class TestEdgeAlignment:
    """边缘标记文字不能被画布边界裁切（底部为信息栏交界处）。"""

    def test_bottom_beat_mark_anchored_up(self, ax):
        col = make_column()
        render_single_column_grid(ax, col, [], is_first_column=True)
        for t in ax.texts:
            if t.get_text() == "0":
                assert t.get_va() == "bottom", "底部拍号应向上生长"

    def test_top_beat_mark_anchored_down(self, ax):
        col = make_column()
        render_single_column_grid(ax, col, [], is_first_column=True)
        for t in ax.texts:
            if t.get_text() == str(COLUMN_BEATS):
                assert t.get_va() == "top", "顶部拍号应向下生长"

    def test_mid_column_beat_mark_centered(self, ax):
        col = make_column()
        render_single_column_grid(ax, col, [], is_first_column=True)
        for t in ax.texts:
            if t.get_text() == str(COLUMN_BEATS // 2):
                assert t.get_va() == "center"

    def test_bpm_at_chart_start_kept_inside(self, ax):
        # BPM 事件位于拍 0 时，原 y-14 锚点会落到画布外，
        # 应折到拍线下方（锚点 > 0）而非被裁切
        bpm_list = [BPMEvent(bpm=174.0, start_time=[0, 0, 1])]
        col = make_column()
        render_single_column_grid(ax, col, bpm_list, is_first_column=True)
        found = [t for t in ax.texts if t.get_text() == "BPM:174"]
        assert len(found) == 1
        assert found[0].get_position()[1] > 0
        assert found[0].get_va() == "top"

    def test_bpm_marker_inside_column_left(self, ax):
        # BPM 标记写在栏内最左侧，与栏外左缘的拍号标记水平错开，不重合
        bpm_list = [BPMEvent(bpm=174.0, start_time=[4, 0, 1])]  # 拍 4，与拍号 "4" 同高度
        col = make_column()
        render_single_column_grid(ax, col, bpm_list, is_first_column=True)
        bpm = [t for t in ax.texts if t.get_text() == "BPM:174"]
        assert len(bpm) == 1
        x = bpm[0].get_position()[0]
        assert col.pixel_left < x < col.pixel_right  # 栏内
        beat_mark = [t for t in ax.texts if t.get_text() == "4"]
        assert len(beat_mark) == 1
        assert abs(x - beat_mark[0].get_position()[0]) > 1.0  # 水平位置不同

    def test_bottom_count_marker_anchored_up(self, ax):
        # 计数标记在每栏底部（拍 0）处不能被信息栏交界处裁切
        col = make_column()
        notes = [
            NoteRenderInfo(
                note=NoteData(type=1, start_time_beat=0.0, end_time_beat=0.0, position_x=0.0),
                true_x=0.0,
                beat=0.0,
                end_beat=0.0,
                is_multitap=False,
                judge_line_name="L",
                column=0,
                x_pixel=0.0,
                y_pixel=0.0,
                y_pixel_end=0.0,
            )
        ]
        render_markers(ax, [col], notes)
        # 拍 0 与拍 4 都有累计计数 "1"；只检查位于底部边缘（y=0）的那一个
        bottom_markers = [
            t for t in ax.texts if t.get_text() == "1" and t.get_position()[1] == 0
        ]
        assert len(bottom_markers) == 1
        assert bottom_markers[0].get_va() == "bottom"

    def test_count_markers_use_actual_smart_column_beats(self, ax):
        column_beats = 36.0
        columns = [
            ColumnInfo(
                index=index,
                beat_start=index * column_beats,
                beat_end=(index + 1) * column_beats,
                pixel_left=index * 600.0,
                pixel_right=index * 600.0 + 450.0,
                pixel_bottom=0.0,
                pixel_top=column_beats * BEAT_HEIGHT_PX,
                column_beats=column_beats,
            )
            for index in range(3)
        ]

        render_markers(ax, columns, [])

        count_positions = {
            (text.get_position()[0], text.get_position()[1])
            for text in ax.texts
            if text.get_text() == "0"
        }
        assert (columns[1].pixel_right + MARKER_MARGIN_PX, 0.0) in count_positions
        assert (
            columns[1].pixel_right + MARKER_MARGIN_PX,
            4.0 * BEAT_HEIGHT_PX,
        ) in count_positions
        assert (columns[2].pixel_right + MARKER_MARGIN_PX, 0.0) in count_positions

    def test_overlap_label_next_to_note(self, ax):
        # 同一开始时间、原始 X 重合的 Note 组标注 "×n"，写在 Note 右侧（栏内）
        notes = [
            NoteRenderInfo(
                note=NoteData(type=1, start_time_beat=0.0, end_time_beat=0.0, position_x=0.0),
                true_x=200.0,
                beat=0.0,
                end_beat=0.0,
                is_multitap=False,
                judge_line_name="L",
                column=0,
                x_pixel=200.0,
                y_pixel=100.0,
                y_pixel_end=0.0,
            ),
            NoteRenderInfo(
                note=NoteData(type=1, start_time_beat=0.0, end_time_beat=0.0, position_x=0.0),
                true_x=200.0,
                beat=0.0,
                end_beat=0.0,
                is_multitap=False,
                judge_line_name="L",
                column=0,
                x_pixel=200.0,
                y_pixel=100.0,
                y_pixel_end=0.0,
            ),
        ]
        render_overlap_markers(ax, notes)
        labels = [t for t in ax.texts if t.get_text() == "×2"]
        assert len(labels) == 1
        x, y = labels[0].get_position()
        # 在 Note 右侧（栏内），垂直位置为开始时间（同刻）
        assert x > 200.0
        assert x < make_column().pixel_right
        assert y == pytest.approx(100.0)
