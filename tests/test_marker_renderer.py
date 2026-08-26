"""marker_renderer 计算函数单元测试（无 matplotlib 依赖路径）。"""

import pytest

from rpe_render.marker_renderer import (
    compute_count_markers,
    compute_interval_markers,
    compute_overlap_groups,
)
from rpe_render.models import NoteData, NoteRenderInfo


def make_info(
    note_type: int,
    beat: float,
    column: int = 0,
    end_beat: float | None = None,
    true_x: float = 0.0,
    x_pixel: float = 0.0,
    y_pixel: float = 0.0,
) -> NoteRenderInfo:
    return NoteRenderInfo(
        note=NoteData(
            type=note_type,
            start_time_beat=beat,
            end_time_beat=end_beat if end_beat is not None else beat,
            position_x=0.0,
        ),
        true_x=true_x,
        beat=beat,
        end_beat=end_beat if end_beat is not None else beat,
        is_multitap=False,
        judge_line_name="L",
        column=column,
        x_pixel=x_pixel,
        y_pixel=y_pixel,
        y_pixel_end=0.0,
    )


class TestIntervalMarkers:
    def test_basic(self):
        notes = [
            make_info(1, 0.0),
            make_info(1, 1 / 16),  # 1/16 拍间隔 = 64 分音符 → "64"
            make_info(1, 2 / 16),
        ]
        markers = compute_interval_markers(notes)
        assert len(markers) == 2
        beats = [m[0] for m in markers]
        labels = [m[2] for m in markers]
        # 标记位于两个 Note 的间隔中点: (0+1/16)/2 与 (1/16+2/16)/2
        assert beats == [pytest.approx(1 / 32), pytest.approx(3 / 32)]
        assert labels == ["64", "64"]

    def test_thirtysecond_note_interval(self):
        # 1/8 拍间隔 = 32 分音符 → 标记 "32"
        notes = [make_info(1, 0.0), make_info(1, 0.125)]
        markers = compute_interval_markers(notes)
        assert markers == [(pytest.approx(0.0625), 0.0, "32")]

    def test_quarter_note_interval_marked(self):
        # 1/4 拍间隔 = 16 分音符 → 标记 "16"（阈值边界，含）
        notes = [make_info(1, 0.0), make_info(1, 0.25)]
        markers = compute_interval_markers(notes)
        assert markers == [(pytest.approx(0.125), 0.0, "16")]

    def test_half_note_interval_not_marked(self):
        # 1/2 拍间隔（八分音符）→ 超过阈值，不标记
        notes = [make_info(1, 0.0), make_info(1, 0.5)]
        assert compute_interval_markers(notes) == []

    def test_filter_types_only_tap_and_hold(self):  # D10
        notes = [
            make_info(3, 0.0),  # Flick 不参与
            make_info(4, 1 / 16),  # Drag 不参与
            make_info(1, 2 / 16),  # Tap 参与
            make_info(2, 3 / 16),  # Hold 参与（跨类型混合排序）
        ]
        markers = compute_interval_markers(notes)
        # Flick/Drag 被剔除后仅剩 Tap@2/16 与 Hold@3/16 一对相邻关系，
        # 标记位于两者中点 (2/16+3/16)/2
        assert len(markers) == 1
        assert markers[0][0] == pytest.approx(5 / 32)
        assert markers[0][2] == "64"

    def test_large_gap_not_marked(self):
        notes = [
            make_info(1, 0.0),
            make_info(1, 1.0),
        ]
        assert compute_interval_markers(notes) == []

    def test_mixed_order_input_sorted_internally(self):
        notes = [
            make_info(2, 4.0 - 1 / 32),
            make_info(1, 0.0),
            make_info(1, 4.0),
        ]
        # 输入乱序，排序后 4-1/32 与 4 相邻间隔 1/32 拍 → 仅一处标记
        markers = compute_interval_markers(notes)
        assert len(markers) == 1
        assert markers[0][2] == str(round(4.0 / (1 / 32)))

    def test_zero_interval_skipped(self):
        notes = [
            make_info(1, 1.0),
            make_info(1, 1.0),  # 完全同刻（多押），间隔 0 不标记
            make_info(1, 1 + 1 / 12),
        ]
        markers = compute_interval_markers(notes)
        assert len(markers) == 1
        # 1/12 拍间隔 → 4/(1/12) = 48 → "48"
        assert markers[0][2] == "48"


class TestOverlapGroups:
    def test_same_start_same_x_grouped(self):
        # 同一开始时间、原始 X 相同 → 一组
        notes = [
            make_info(1, 0.0, true_x=200.0),
            make_info(1, 0.0, true_x=200.0),
            make_info(1, 0.0, true_x=220.0),
        ]
        groups = compute_overlap_groups(notes)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_threshold_boundary(self):
        # 原始 X 距离恰为阈值 75 → 重合；> 阈值 → 不重合
        inside = [
            make_info(1, 0.0, true_x=0.0),
            make_info(1, 0.0, true_x=75.0),
        ]
        assert len(compute_overlap_groups(inside)) == 1

        outside = [
            make_info(1, 0.0, true_x=0.0),
            make_info(1, 0.0, true_x=76.0),
        ]
        assert compute_overlap_groups(outside) == []

    def test_different_start_not_grouped(self):
        # 只看开始时间：不同开始时间的 Note 即使位置接近也不成组
        # （Hold 持续时间内覆盖的音符即属此类：startTime 不同）
        notes = [
            make_info(1, 0.0, true_x=0.0),
            make_info(1, 1 / 16, true_x=0.0),  # 渲染位置很近（6px），但不同刻
        ]
        assert compute_overlap_groups(notes) == []

    def test_hold_head_only(self):
        # Hold 仅以头部参与：与 Hold 同刻的 Tap 成组；
        # Hold 持续期间内的 Tap（startTime 不同）不与其成组
        hold = make_info(2, 4.0, end_beat=8.0, true_x=0.0)
        tap_inside = make_info(1, 5.0, true_x=0.0)  # Hold 持续期间
        tap_same_start = make_info(1, 4.0, true_x=0.0)  # 与 Hold 头同刻
        assert compute_overlap_groups([hold, tap_inside]) == []
        groups = compute_overlap_groups([hold, tap_inside, tap_same_start])
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_custom_threshold(self):
        notes = [
            make_info(1, 0.0, true_x=0.0),
            make_info(1, 0.0, true_x=60.0),
        ]
        assert compute_overlap_groups(notes, threshold_x=50.0) == []
        assert len(compute_overlap_groups(notes, threshold_x=80.0)) == 1

    def test_subclusters_within_same_start(self):
        # 同刻多个 Note 按原始 X 距离细分：0 与 40 成组，200 单独不成组
        notes = [
            make_info(1, 0.0, true_x=0.0),
            make_info(1, 0.0, true_x=40.0),
            make_info(1, 0.0, true_x=200.0),
        ]
        groups = compute_overlap_groups(notes)
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_no_overlap(self):
        notes = [
            make_info(1, 0.0, true_x=0.0),
            make_info(1, 0.0, true_x=300.0),
            make_info(1, 1.0, true_x=0.0),
        ]
        assert compute_overlap_groups(notes) == []

    def test_two_separate_groups(self):
        notes = [
            make_info(1, 0.0, true_x=100.0),
            make_info(1, 0.0, true_x=100.0),
            make_info(1, 0.0, true_x=300.0),
            make_info(1, 0.0, true_x=300.0),
            make_info(1, 0.0, true_x=300.0),
        ]
        groups = compute_overlap_groups(notes)
        assert len(groups) == 2
        assert sorted(len(g) for g in groups) == [2, 3]


class TestCountMarkers:
    def test_cumulative(self):
        notes = [
            make_info(1, 1.0),
            make_info(1, 5.0),
            make_info(1, 9.0),
        ]
        markers = compute_count_markers(notes, max_beat=12.0)
        counts = {int(b): c for b, _, c in markers}
        assert counts[0] == 0
        assert counts[4] == 1
        assert counts[8] == 2
        assert counts[12] == 3

    def test_column_index(self):
        notes = [make_info(1, 70.0)]
        markers = compute_count_markers(notes, max_beat=72.0)
        by_beat = {int(b): col for b, col, _ in markers}
        assert by_beat[64] == 1  # 第 2 栏

    def test_empty_notes(self):
        assert compute_count_markers([], max_beat=8.0) == [
            (0.0, 0.0, 0),
            (4.0, 0.0, 0),
            (8.0, 0.0, 0),
        ]

    def test_boundary_inclusive(self):
        # 恰好在 check_beat 上的音符应被计入（含）
        notes = [make_info(1, 4.0)]
        markers = compute_count_markers(notes, max_beat=4.0)
        by_beat = {int(b): c for b, _, c in markers}
        assert by_beat[4] == 1
