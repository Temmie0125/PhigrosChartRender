"""affected_area_renderer 单元测试（段构建 + 白框/小区域渲染）。"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from rpe_render.affected_area_renderer import (
    affected_column_indices,
    build_affected_segments,
    compute_affected_area_widths,
    render_affected_areas,
    render_affected_boxes,
    _normalize_angle,
)
from rpe_render.constants import (
    AFFECTED_AREA_MARGIN_LEFT_PX,
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    COLUMN_GAP,
    COLUMN_WIDTH,
    GAME_X_MAX,
    GAME_X_MIN,
    NOTE_ICON_WIDTH,
)
from rpe_render.models import NoteData, NoteRenderInfo
from rpe_render.timeline import compute_columns


def make_info(
    beat: float,
    pos_x: float = 0.0,
    angle: float = 0.0,
    note_type: int = 1,
    end_beat: float | None = None,
    column: int | None = None,
    judge_line=None,
    judge_line_name: str = "L",
) -> NoteRenderInfo:
    end = end_beat if end_beat is not None else beat
    note = NoteData(
        type=note_type,
        start_time_beat=beat,
        end_time_beat=end,
        position_x=pos_x,
    )
    return NoteRenderInfo(
        note=note,
        true_x=0.0,
        beat=beat,
        end_beat=end,
        is_multitap=False,
        judge_line_name=judge_line_name,
        column=column if column is not None else int(beat // COLUMN_BEATS),
        x_pixel=0.0,
        y_pixel=0.0,
        y_pixel_end=0.0,
        judge_line=judge_line,
        line_angle=angle,
    )


class TestNormalizeAngle:
    def test_quadrants(self):
        assert _normalize_angle(0.0) == 0.0
        assert _normalize_angle(90.0) == 90.0
        assert _normalize_angle(-90.0) == -90.0
        assert _normalize_angle(180.0) == 180.0
        assert _normalize_angle(-180.0) == 180.0  # -180 % 360 = 180

    def test_wrap_around(self):
        # 270° 等价 -90°
        assert _normalize_angle(270.0) == -90.0
        assert _normalize_angle(-270.0) == 90.0
        assert _normalize_angle(360.0) == 0.0
        assert _normalize_angle(400.0) == 40.0
        assert _normalize_angle(-370.0) == -10.0


class TestBuildAffectedSegments:
    def test_boundaries(self):
        # 74.9 否、75 是、90 是、90.1 否
        infos = [
            make_info(1.0, angle=74.9),
            make_info(2.0, angle=75.0),
            make_info(3.0, angle=90.0),
            make_info(4.0, angle=90.1),
        ]
        segs = build_affected_segments(infos)
        assert len(segs) == 1
        assert [n.beat for n in segs[0].notes] == [2.0, 3.0]

    def test_negative_and_wrapped_angles(self):
        infos = [
            make_info(1.0, angle=-75.0),
            make_info(2.0, angle=-90.0),
            make_info(3.0, angle=270.0),  # 归一化 -90°
            make_info(4.0, angle=-74.0),
        ]
        segs = build_affected_segments(infos)
        assert len(segs) == 1
        assert [n.beat for n in segs[0].notes] == [1.0, 2.0, 3.0]

    def test_consecutive_aggregated(self):
        infos = [make_info(10.0, angle=80.0), make_info(12.0, angle=80.0), make_info(14.0, angle=80.0)]
        segs = build_affected_segments(infos)
        assert len(segs) == 1
        assert segs[0].beat_start == 10.0
        assert segs[0].beat_end == 14.0

    def test_unaffected_note_breaks_segment(self):
        infos = [
            make_info(10.0, angle=80.0),
            make_info(11.0, angle=80.0),
            make_info(12.0, angle=0.0),  # 夹在中间 → 断段
            make_info(13.0, angle=80.0),
        ]
        segs = build_affected_segments(infos)
        assert len(segs) == 2
        assert [n.beat for n in segs[0].notes] == [10.0, 11.0]
        assert [n.beat for n in segs[1].notes] == [13.0]

    def test_hold_affected_by_start_angle_and_end_included(self):
        infos = [make_info(20.0, angle=85.0, note_type=2, end_beat=26.0)]
        segs = build_affected_segments(infos)
        assert len(segs) == 1
        assert segs[0].beat_start == 20.0
        assert segs[0].beat_end == 26.0  # Hold 段含 end_beat

    def test_hold_unaffected_skipped(self):
        infos = [make_info(20.0, angle=0.0, note_type=2, end_beat=26.0)]
        assert build_affected_segments(infos) == []

    def test_grouped_by_judge_line(self):
        line_a = object()
        line_b = object()
        infos = [
            make_info(10.0, angle=80.0, judge_line=line_a),
            make_info(12.0, angle=80.0, judge_line=line_b),
        ]
        segs = build_affected_segments(infos)
        assert len(segs) == 2

    def test_name_fallback_grouping(self):
        infos = [
            make_info(10.0, angle=80.0, judge_line_name="A"),
            make_info(11.0, angle=80.0, judge_line_name="A"),
            make_info(12.0, angle=80.0, judge_line_name="B"),
        ]
        segs = build_affected_segments(infos)
        assert len(segs) == 2
        assert [n.beat for n in segs[0].notes] == [10.0, 11.0]
        assert [n.beat for n in segs[1].notes] == [12.0]

    def test_cross_column_segment_column_set(self):
        infos = [
            make_info(10.0, angle=80.0),
            make_info(12.0, angle=80.0),
            make_info(66.0, angle=80.0),
            make_info(68.0, angle=80.0),
        ]
        segs = build_affected_segments(infos)
        assert len(segs) == 1
        assert affected_column_indices(segs) == {0, 1}

    def test_cross_column_hold_extends_column_set(self):
        # Hold 60→70 拍跨越栏 0/1，且按 startTime（60 拍）判定受影响
        infos = [make_info(60.0, angle=80.0, note_type=2, end_beat=70.0)]
        segs = build_affected_segments(infos)
        assert len(segs) == 1
        assert affected_column_indices(segs) == {0, 1}


class TestRenderAffectedBoxes:
    @pytest.fixture()
    def ax(self):
        fig = plt.figure(figsize=(4, 8), dpi=100)
        axes = fig.add_axes([0, 0, 1, 1])
        axes.set_xlim(0, 1050)
        axes.set_ylim(0, COLUMN_BEATS * BEAT_HEIGHT_PX)
        yield axes
        plt.close(fig)

    def test_box_extent_covers_notes(self, ax):
        note_a = make_info(10.0, angle=80.0)
        note_b = make_info(12.0, angle=80.0)
        note_a.x_pixel = 100.0
        note_b.x_pixel = 300.0
        columns = compute_columns(16.0)
        segs = build_affected_segments([note_a, note_b])
        render_affected_boxes(ax, columns, segs, image_loader=None)

        patches = [p for p in ax.patches if type(p).__name__ == "FancyBboxPatch"]
        assert len(patches) == 1
        bbox = patches[0].get_bbox()
        half = NOTE_ICON_WIDTH / 2 + 6.0
        assert bbox.x0 == pytest.approx(100.0 - half)
        assert bbox.x1 == pytest.approx(300.0 + half)
        assert bbox.y0 == pytest.approx(10.0 * BEAT_HEIGHT_PX - 6.0)
        assert bbox.y1 == pytest.approx(12.0 * BEAT_HEIGHT_PX + 6.0)
        # 空心：仅描边，无填充
        assert patches[0].get_facecolor()[3] == 0.0
        assert patches[0].get_edgecolor()[:3] == pytest.approx((1.0, 1.0, 1.0))

    def test_cross_column_box_per_column(self, ax):
        notes = [
            make_info(10.0, pos_x=-300.0, angle=80.0),
            make_info(66.0, pos_x=200.0, angle=80.0),
        ]
        notes[0].x_pixel = 125.0
        notes[1].x_pixel = 720.0 + 325.0
        columns = compute_columns(70.0, affected_columns={0, 1})
        segs = build_affected_segments(notes)
        render_affected_boxes(ax, columns, segs, image_loader=None)

        patches = [p for p in ax.patches if type(p).__name__ == "FancyBboxPatch"]
        assert len(patches) == 2  # 两栏各一个簇（间隔 56 拍 > 阈值 → 拆开）
        # 每个框只包住本栏实际音符，不框无 note 段落
        box0 = patches[0].get_bbox()
        assert box0.x0 == pytest.approx(125.0 - NOTE_ICON_WIDTH / 2 - 6.0)
        assert box0.y1 - box0.y0 == pytest.approx(12.0)  # 仅 beat 10
        box1 = patches[1].get_bbox()
        assert box1.x0 == pytest.approx(
            720.0 + 325.0 - NOTE_ICON_WIDTH / 2 - 6.0
        )
        assert box1.y1 - box1.y0 == pytest.approx(12.0)  # 仅 beat 66

    def test_large_gap_splits_box(self, ax):
        # 段内相邻 note 间隔 > 阈值 → 拆成独立白框（无 note 段落不框）
        notes = [
            make_info(10.0, angle=80.0),
            make_info(12.0, angle=80.0),
            make_info(60.0, angle=80.0),
        ]
        for n, x in zip(notes, (100.0, 150.0, 300.0)):
            n.x_pixel = x
        columns = compute_columns(64.0)
        segs = build_affected_segments(notes)
        render_affected_boxes(ax, columns, segs, None)

        patches = [p for p in ax.patches if type(p).__name__ == "FancyBboxPatch"]
        assert len(patches) == 2
        box0 = patches[0].get_bbox()
        assert box0.y1 == pytest.approx(12.0 * BEAT_HEIGHT_PX + 6.0)
        box1 = patches[1].get_bbox()  # 仅 beat 60 的短框
        assert box1.y1 - box1.y0 == pytest.approx(12.0)
        assert box1.y0 == pytest.approx(60.0 * BEAT_HEIGHT_PX - 6.0)

    def test_merge_overlapping_boxes(self, ax):
        # 两条判定线的受影响簇在同一栏同一时刻相重 → 合并为一个框
        line_a = object()
        line_b = object()
        notes = [
            make_info(10.0, pos_x=-300.0, angle=80.0, judge_line=line_a),
            make_info(10.0, pos_x=300.0, angle=80.0, judge_line=line_b),
        ]
        notes[0].x_pixel = 225.0  # 同刻同区域 → 白框重合
        notes[1].x_pixel = 240.0
        columns = compute_columns(16.0, affected_columns={0})
        segs = build_affected_segments(notes)
        render_affected_boxes(ax, columns, segs, image_loader=None)

        patches = [p for p in ax.patches if type(p).__name__ == "FancyBboxPatch"]
        assert len(patches) == 1  # 重合白框合并
        bbox = patches[0].get_bbox()
        assert bbox.x0 == pytest.approx(225.0 - NOTE_ICON_WIDTH / 2 - 6.0)
        assert bbox.x1 == pytest.approx(240.0 + NOTE_ICON_WIDTH / 2 + 6.0)
        assert bbox.y0 == pytest.approx(10.0 * BEAT_HEIGHT_PX - 6.0)
        assert bbox.y1 == pytest.approx(10.0 * BEAT_HEIGHT_PX + 6.0)

    def test_disjoint_boxes_not_merged(self, ax):
        # 时间岔开的簇不合并
        notes = [
            make_info(10.0, pos_x=0.0, angle=80.0),
            make_info(40.0, pos_x=0.0, angle=80.0),
        ]
        for n in notes:
            n.x_pixel = 225.0
        columns = compute_columns(64.0)
        segs = build_affected_segments(notes)
        render_affected_boxes(ax, columns, segs, None)

        patches = [p for p in ax.patches if type(p).__name__ == "FancyBboxPatch"]
        assert len(patches) == 2

    def test_hold_cluster_contained_in_box(self, ax):
        # 跨栏 Hold：框只覆盖其在栏内实际存在的时间段
        hold = make_info(60.0, pos_x=0.0, angle=80.0, note_type=2, end_beat=70.0)
        hold.x_pixel = 225.0
        columns = compute_columns(70.0, affected_columns={0, 1})
        segs = build_affected_segments([hold])
        render_affected_boxes(ax, columns, segs, None)

        patches = [p for p in ax.patches if type(p).__name__ == "FancyBboxPatch"]
        assert len(patches) == 2
        box0 = patches[0].get_bbox()
        assert box0.y0 == pytest.approx(60.0 * BEAT_HEIGHT_PX - 6.0)
        assert box0.y1 == pytest.approx(64.0 * BEAT_HEIGHT_PX + 6.0)
        box1 = patches[1].get_bbox()
        assert box1.y0 == pytest.approx(-6.0)
        assert box1.y1 == pytest.approx(6.0 * BEAT_HEIGHT_PX + 6.0)


class _StubLoader:
    """54x54 空白贴图假加载器。"""

    def get_note_image(self, note_type, is_hl):
        return np.full((54, 54, 4), 255, dtype=np.uint8)

    def get_hold_body_image(self, note_type, is_hl, target_height_px):
        return np.full((max(1, target_height_px), 54, 4), 255, dtype=np.uint8)

    def get_hold_end_image(self, is_hl):
        return np.full((54, 54, 4), 255, dtype=np.uint8)


class TestRenderAffectedAreas:
    @pytest.fixture()
    def ax(self):
        fig = plt.figure(figsize=(8, 8), dpi=100)
        axes = fig.add_axes([0, 0, 1, 1])
        axes.set_xlim(0, 1400)
        axes.set_ylim(0, COLUMN_BEATS * BEAT_HEIGHT_PX)
        yield axes
        plt.close(fig)

    def _area_extent(self, columns, col_index, segs):
        col = columns[col_index]
        left = col.pixel_right + AFFECTED_AREA_MARGIN_LEFT_PX
        width = compute_affected_area_widths(segs)[col_index]
        return left, left + width

    def test_area_background_and_icons(self, ax):
        notes = [
            make_info(10.0, pos_x=-300.0, angle=80.0),
            make_info(12.0, pos_x=300.0, angle=80.0),
        ]
        columns = compute_columns(16.0, affected_columns={0})
        segs = build_affected_segments(notes)
        loader = _StubLoader()
        render_affected_areas(ax, columns, segs, loader)

        # 背景矩形：与受影响区域等高（beat 10~12），不填满整栏
        rects = [p for p in ax.patches if type(p).__name__ == "Rectangle"]
        assert len(rects) == 1
        left, right = self._area_extent(columns, 0, segs)
        rect = rects[0]
        assert rect.get_xy()[0] == pytest.approx(left)
        assert rect.get_width() == pytest.approx(right - left)
        assert rect.get_xy()[1] == pytest.approx(10.0 * BEAT_HEIGHT_PX)
        assert rect.get_height() == pytest.approx(2.0 * BEAT_HEIGHT_PX)
        # 背景与主栏轨道一致：半透明黑覆盖层（无白色填充）
        assert rect.get_alpha() == pytest.approx(0.75)
        assert rect.get_facecolor()[0] == pytest.approx(0.0)
        assert rect.get_edgecolor()[0] == pytest.approx(0.8)  # #CCCCCC

        # 区域宽度 = 真实占用宽度（最左 note 左端 ~ 最右 note 右端）：
        # 600 单位 positionX 差 × 主栏比例 + 图标宽
        assert right - left == pytest.approx(
            600.0 / (GAME_X_MAX - GAME_X_MIN) * COLUMN_WIDTH + NOTE_ICON_WIDTH
        )

        # 区域内图标：真实间距放置（与主栏同比例），最左 note 左端对齐区域左缘
        images = ax.get_images()
        assert len(images) == 2
        centers = []
        for img, note in zip(images, notes):
            x0, x1, y0, y1 = img.get_extent()
            assert x0 >= left
            assert x1 <= right
            # 图标中心 Y 对应 note 拍数
            assert (y0 + y1) / 2 == pytest.approx(
                (note.beat - 0) * BEAT_HEIGHT_PX
            )
            # 54px 图标宽度
            assert x1 - x0 == pytest.approx(NOTE_ICON_WIDTH)
            centers.append((x0 + x1) / 2)
        # 两图标中心距 = positionX 差 × 主栏比例（不再固定宽度压缩）
        assert centers[1] - centers[0] == pytest.approx(
            600.0 / (GAME_X_MAX - GAME_X_MIN) * COLUMN_WIDTH
        )
        # 最左 note 左端恰好对齐区域左缘
        assert images[0].get_extent()[0] == pytest.approx(left)

    def test_area_height_follows_segment(self, ax):
        # 多段时区域覆盖受影响范围（min 起拍 ~ max 结束拍）
        notes = [
            make_info(10.0, pos_x=0.0, angle=80.0),
            make_info(20.0, pos_x=0.0, angle=80.0),
        ]
        columns = compute_columns(24.0, affected_columns={0})
        segs = build_affected_segments(notes)
        loader = _StubLoader()
        render_affected_areas(ax, columns, segs, loader)

        rects = [p for p in ax.patches if type(p).__name__ == "Rectangle"]
        assert len(rects) == 1
        rect = rects[0]
        assert rect.get_xy()[1] == pytest.approx(10.0 * BEAT_HEIGHT_PX)
        assert rect.get_height() == pytest.approx(10.0 * BEAT_HEIGHT_PX)

    def test_area_background_skipped_when_alpha_zero(self, ax):
        notes = [make_info(10.0, pos_x=0.0, angle=80.0)]
        columns = compute_columns(16.0, affected_columns={0})
        segs = build_affected_segments(notes)
        loader = _StubLoader()
        render_affected_areas(ax, columns, segs, loader, track_bg_alpha=0.0)
        assert list(ax.patches) == []
        assert len(ax.get_images()) == 1  # 图标仍渲染

    def test_hold_piece_in_area(self, ax):
        hold = make_info(10.0, pos_x=0.0, angle=80.0, note_type=2, end_beat=12.0)
        columns = compute_columns(16.0, affected_columns={0})
        segs = build_affected_segments([hold])
        loader = _StubLoader()
        render_affected_areas(ax, columns, segs, loader)

        # 背景矩形与 Hold 段等高（beat 10~12）
        rects = [p for p in ax.patches if type(p).__name__ == "Rectangle"]
        assert len(rects) == 1
        rect = rects[0]
        assert rect.get_xy()[1] == pytest.approx(10.0 * BEAT_HEIGHT_PX)
        assert rect.get_height() == pytest.approx(2.0 * BEAT_HEIGHT_PX)

        images = ax.get_images()
        # Head + Body + End 三段贴图（绘制顺序：Head、End、Body）
        assert len(images) == 3
        left, right = self._area_extent(columns, 0, segs)
        assert all(
            img.get_extent()[0] >= left and img.get_extent()[1] <= right
            for img in images
        )
        # Head 中心在 beat 10，End 中心在 beat 12
        head = images[0]
        end = images[1]
        assert (head.get_extent()[2] + head.get_extent()[3]) / 2 == pytest.approx(
            10.0 * BEAT_HEIGHT_PX
        )
        assert (end.get_extent()[2] + end.get_extent()[3]) / 2 == pytest.approx(
            12.0 * BEAT_HEIGHT_PX
        )

    def test_cross_column_hold_area_pieces(self, ax):
        hold = make_info(60.0, pos_x=100.0, angle=80.0, note_type=2, end_beat=70.0)
        columns = compute_columns(70.0, affected_columns={0, 1})
        segs = build_affected_segments([hold])
        loader = _StubLoader()
        render_affected_areas(ax, columns, segs, loader)

        # 两个受影响栏各绘制区域背景 + 内容
        rects = [p for p in ax.patches if type(p).__name__ == "Rectangle"]
        assert len(rects) == 2
        # 各栏区域与 Hold 在该栏内的段等高：栏 0 [60,64]，栏 1 [64,70]
        rect0, rect1 = rects
        assert rect0.get_xy()[1] == pytest.approx(60.0 * BEAT_HEIGHT_PX)
        assert rect0.get_height() == pytest.approx(4.0 * BEAT_HEIGHT_PX)
        assert rect1.get_xy()[1] == pytest.approx(0.0)
        assert rect1.get_height() == pytest.approx(6.0 * BEAT_HEIGHT_PX)
        images = ax.get_images()
        # 栏 0：Head + Body（补满到栏顶）；栏 1：Body + End
        assert len(images) == 4
        # 所有贴图都落在各自栏的右间隙内
        for col_index in (0, 1):
            left, right = self._area_extent(columns, col_index, segs)
            col_imgs = [
                img
                for img in images
                if left - 1 <= img.get_extent()[0] <= right + 1
            ]
            assert len(col_imgs) == 2
            assert all(
                img.get_extent()[0] >= left - 1 and img.get_extent()[1] <= right + 1
                for img in col_imgs
            )

    def test_same_beat_note_above_hold(self, ax):
        # 同刻 Hold 与普通 Note：非 Hold Note 分配更高 zorder 绘制在上层，
        # 避免 Hold 头遮挡与之重合的音符
        hold = make_info(10.0, pos_x=0.0, angle=80.0, note_type=2, end_beat=12.0)
        tap = make_info(10.0, pos_x=100.0, angle=80.0)
        columns = compute_columns(16.0, affected_columns={0})
        segs = build_affected_segments([hold, tap])
        loader = _StubLoader()
        render_affected_areas(ax, columns, segs, loader)

        images = ax.get_images()
        # Hold 段 3 张贴图（Head/Body/End）zorder 相同且较低；Tap 图标在上层
        hold_z = images[0].get_zorder()
        assert all(img.get_zorder() == hold_z for img in images[:3])
        tap_img = images[3]
        assert tap_img.get_zorder() > hold_z
        # Tap 图标位置按真实间距映射：锚点 p_min=0（Hold 的 pos_x），
        # pos_x 100 → 主栏比例 33.3px + 半图标宽
        left = 450 + AFFECTED_AREA_MARGIN_LEFT_PX
        expected_cx = (
            left
            + 100.0 / (GAME_X_MAX - GAME_X_MIN) * COLUMN_WIDTH
            + NOTE_ICON_WIDTH / 2
        )
        assert (tap_img.get_extent()[0] + tap_img.get_extent()[1]) / 2 == pytest.approx(
            expected_cx
        )

    def test_unaffected_column_no_area(self, ax):
        notes = [make_info(10.0, pos_x=0.0, angle=0.0)]
        columns = compute_columns(16.0)
        segs = build_affected_segments(notes)
        loader = _StubLoader()
        render_affected_areas(ax, columns, segs, loader)
        assert list(ax.patches) == []
        assert ax.get_images() == []
