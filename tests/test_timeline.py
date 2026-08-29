"""timeline 单元测试（纯计算，无 matplotlib 渲染）。"""

import pytest

from rpe_render.constants import (
    AFFECTED_AREA_EXTRA_GAP_PX,
    AFFECTED_AREA_MARGIN_LEFT_PX,
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    COLUMN_GAP,
    COLUMN_WIDTH,
    INFO_BAR_HEIGHT_PX,
)
from rpe_render.chart_parser import parse_chart
from rpe_render.timeline import (
    beat_to_pixel,
    compute_canvas_size,
    compute_columns,
    compute_max_beat,
    compute_smart_column_beats,
    merge_all_notes,
    x_to_pixel,
)


class TestComputeColumns:
    def test_single_column(self):
        cols = compute_columns(40.0)
        assert len(cols) == 1
        assert cols[0].beat_start == 0.0
        assert cols[0].beat_end == COLUMN_BEATS

    def test_exact_boundary(self):
        # max_beat=64 属于第 2 栏的开始，第 1 栏覆盖 [0, 64]
        cols = compute_columns(64.0)
        assert len(cols) == 1

    def test_multi(self):
        cols = compute_columns(200.0)
        assert len(cols) == 4
        for i, col in enumerate(cols):
            assert col.index == i
            assert col.pixel_left == i * (COLUMN_WIDTH + COLUMN_GAP)
            assert col.pixel_right == col.pixel_left + COLUMN_WIDTH
            assert col.pixel_bottom == 0.0
            assert col.pixel_top == COLUMN_BEATS * BEAT_HEIGHT_PX

    def test_zero_beats_still_one_column(self):
        assert len(compute_columns(0.0)) == 1

    def test_custom_column_beats(self):
        cols = compute_columns(100.0, column_beats=20)
        assert len(cols) == 5
        assert all(col.column_beats == 20 for col in cols)
        assert cols[-1].beat_start == 80
        assert cols[-1].beat_end == 100


class TestSmartColumnBeats:
    def test_returns_aligned_positive_value(self):
        value = compute_smart_column_beats(200.0)
        assert value >= 4
        assert value % 4 == 0

    def test_improves_ratio_against_fixed_default_for_long_chart(self):
        from math import ceil, log

        from rpe_render.constants import (
            COLUMN_GAP,
            COLUMN_WIDTH,
            INFO_BAR_HEIGHT_PX,
            BEAT_HEIGHT_PX,
            SIDE_MARKER_PADDING_PX,
        )

        total = 200.0
        target = 16 / 9

        def error(beats):
            columns = max(1, int(ceil(total / beats)))
            ratio = (
                columns * COLUMN_WIDTH
                + max(columns - 1, 0) * COLUMN_GAP
                + 2 * SIDE_MARKER_PADDING_PX
            ) / (beats * BEAT_HEIGHT_PX + INFO_BAR_HEIGHT_PX)
            return abs(log(ratio / target))

        assert error(compute_smart_column_beats(total)) <= error(COLUMN_BEATS)


class TestComputeColumnsAffected:
    def test_affected_column_extra_gap(self):
        cols = compute_columns(200.0, affected_columns={0, 1})
        # 栏 0 受影响：自身右侧额外间距
        assert cols[0].pixel_left == 0.0
        assert cols[0].pixel_gap_right == pytest.approx(AFFECTED_AREA_EXTRA_GAP_PX)
        # 栏 1 左缘 = 栏 0 宽 + 间距 + 栏 0 的额外间距
        assert cols[1].pixel_left == pytest.approx(
            COLUMN_WIDTH + COLUMN_GAP + AFFECTED_AREA_EXTRA_GAP_PX
        )
        assert cols[1].pixel_gap_right == pytest.approx(AFFECTED_AREA_EXTRA_GAP_PX)
        # 栏 2 左缘累积了两段位移（栏 0 额外间距 + 栏 1 额外间距）
        assert cols[2].pixel_left == pytest.approx(
            2 * (COLUMN_WIDTH + COLUMN_GAP) + 2 * AFFECTED_AREA_EXTRA_GAP_PX
        )
        assert cols[2].pixel_gap_right == 0.0

    def test_default_unchanged(self):
        cols = compute_columns(200.0)
        for i, col in enumerate(cols):
            assert col.pixel_left == i * (COLUMN_WIDTH + COLUMN_GAP)
            assert col.pixel_gap_right == 0.0

    def test_empty_set_same_as_none(self):
        assert compute_columns(70.0, affected_columns=set()) == compute_columns(70.0)

    def test_affected_column_dynamic_gap(self):
        # 小区域宽度超出默认预留时，该栏间距放大到 MARGIN_LEFT + 宽度
        cols = compute_columns(
            200.0,
            affected_columns={0, 1},
            column_area_widths={0: 300.0, 1: 50.0},
        )
        assert cols[0].pixel_gap_right == pytest.approx(
            AFFECTED_AREA_MARGIN_LEFT_PX + 300.0
        )
        assert cols[1].pixel_left == pytest.approx(
            COLUMN_WIDTH + COLUMN_GAP + AFFECTED_AREA_MARGIN_LEFT_PX + 300.0
        )
        # 宽度不足默认值时仍取默认 150
        assert cols[1].pixel_gap_right == pytest.approx(AFFECTED_AREA_EXTRA_GAP_PX)
        # 无区域宽度信息时行为与旧版一致
        cols_default = compute_columns(200.0, affected_columns={0, 1})
        assert cols_default[0].pixel_gap_right == pytest.approx(
            AFFECTED_AREA_EXTRA_GAP_PX
        )


class TestBeatToPixelAffected:
    def test_x_offset_matches_column_pixel_left(self):
        cols = compute_columns(200.0, affected_columns={0})
        for beat in (10.0, 70.0, 130.0):
            col, _, x_off = beat_to_pixel(beat, cols)
            assert x_off == pytest.approx(cols[col].pixel_left)

    def test_x_offset_includes_extra_gap(self):
        cols = compute_columns(200.0, affected_columns={0})
        col, _, x_off = beat_to_pixel(70.0, cols)
        assert col == 1
        assert x_off == pytest.approx(
            COLUMN_WIDTH + COLUMN_GAP + AFFECTED_AREA_EXTRA_GAP_PX
        )
class TestBeatToPixel:
    def test_basic_mapping(self):
        cols = compute_columns(200.0)
        col, y, x_off = beat_to_pixel(0.0, cols)
        assert (col, y, x_off) == (0, 0.0, 0.0)

    def test_mid_column(self):
        cols = compute_columns(200.0)
        col, y, x_off = beat_to_pixel(32.5, cols)
        assert col == 0
        assert y == pytest.approx(32.5 * BEAT_HEIGHT_PX)

    def test_second_column(self):
        cols = compute_columns(200.0)
        col, y, x_off = beat_to_pixel(70.0, cols)
        assert col == 1
        assert y == pytest.approx(6 * BEAT_HEIGHT_PX)
        assert x_off == COLUMN_WIDTH + COLUMN_GAP

    def test_out_of_range_raises(self):
        cols = compute_columns(64.0)
        with pytest.raises(ValueError):
            beat_to_pixel(100.0, cols)


class TestXToPixel:
    def test_center_maps_to_middle(self):
        left = 600.0
        assert x_to_pixel(0.0, left) == pytest.approx(left + COLUMN_WIDTH / 2)

    def test_full_range(self):
        from rpe_render.constants import GAME_X_MAX, GAME_X_MIN

        assert x_to_pixel(GAME_X_MIN, 0.0) == pytest.approx(0.0)
        assert x_to_pixel(GAME_X_MAX, 0.0) == pytest.approx(COLUMN_WIDTH)

    def test_out_of_range_clamped(self):
        assert x_to_pixel(-9999.0, 0.0) == 0.0
        assert x_to_pixel(9999.0, 0.0) == COLUMN_WIDTH


class TestChartDerived:
    def test_compute_max_beat_and_merge(self, minimal_chart_path):
        chart = parse_chart(minimal_chart_path)
        notes = merge_all_notes(chart)
        # isFake 已过滤：2 个 note
        assert len(notes) == 2
        # hold endTime=8 拍
        assert compute_max_beat(chart) == pytest.approx(8.0)

    def test_max_beat_fallback_to_bpm(self, tmp_path, minimal_chart_path):
        import json

        raw = json.loads(minimal_chart_path.read_text(encoding="utf-8"))
        raw["judgeLineList"][0]["notes"] = []
        p = tmp_path / "nonotes.json"
        p.write_text(json.dumps(raw), encoding="utf-8")
        chart = parse_chart(p)
        # BPMList 最后一个 startTime = 32 拍
        assert compute_max_beat(chart) == pytest.approx(32.0)


class TestCanvasSize:
    def test_size(self):
        from rpe_render.constants import OUTPUT_DPI, SIDE_MARKER_PADDING_PX

        cols = compute_columns(200.0)
        w_in, h_in = compute_canvas_size(cols)
        # 画布宽度包含两侧标记边距
        expected_w = (
            cols[-1].pixel_right + 2 * SIDE_MARKER_PADDING_PX
        ) / OUTPUT_DPI
        expected_h = (COLUMN_BEATS * BEAT_HEIGHT_PX + INFO_BAR_HEIGHT_PX) / OUTPUT_DPI
        assert w_in == pytest.approx(expected_w)
        assert h_in == pytest.approx(expected_h)

    def test_size_includes_last_extra_gap(self):
        from rpe_render.constants import OUTPUT_DPI, SIDE_MARKER_PADDING_PX

        cols = compute_columns(200.0, affected_columns={3})  # 末栏受影响
        w_in, _ = compute_canvas_size(cols)
        expected_w = (
            cols[-1].pixel_right
            + cols[-1].pixel_gap_right
            + 2 * SIDE_MARKER_PADDING_PX
        ) / OUTPUT_DPI
        assert w_in == pytest.approx(expected_w)
        assert w_in > (
            cols[-1].pixel_right + 2 * SIDE_MARKER_PADDING_PX
        ) / OUTPUT_DPI
