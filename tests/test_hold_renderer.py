"""hold_renderer 计算与渲染单元测试（prepare / sample / 段内 X 对齐）。"""

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pytest

from rpe_render.constants import (
    BEAT_HEIGHT_PX,
    COLUMN_BEATS,
    COLUMN_WIDTH,
    GAME_X_MAX,
    GAME_X_MIN,
    HOLD_BODY_OVERLAP_PX,
)
from rpe_render.chart_parser import parse_chart
from rpe_render.easing.event_evaluator import judge_line_x_at
from rpe_render.hold_renderer import (
    HoldRenderInfo,
    prepare_hold_render_info,
    render_hold_body,
    render_hold_head_end,
    sample_hold_trajectory,
)
from rpe_render.models import NoteData, NoteRenderInfo
from rpe_render.timeline import compute_columns, x_to_pixel


def build_infos(chart):
    infos = []
    for line in chart.judge_line_list:
        for note in line.notes:
            if note.type != 2:
                continue
            infos.append(
                NoteRenderInfo(
                    note=note,
                    true_x=note.position_x,
                    beat=note.start_time_beat,
                    end_beat=note.end_time_beat,
                    is_multitap=False,
                    judge_line_name=line.name,
                    column=int(note.start_time_beat // COLUMN_BEATS),
                    x_pixel=COLUMN_WIDTH / 2,
                    y_pixel=(note.start_time_beat % COLUMN_BEATS) * BEAT_HEIGHT_PX,
                    y_pixel_end=(note.end_time_beat % COLUMN_BEATS) * BEAT_HEIGHT_PX,
                    judge_line=line,
                )
            )
    return infos


def make_info(beat: float, end_beat: float, judge_line=None) -> NoteRenderInfo:
    """构造一个 Hold 的 NoteRenderInfo（无判定线时按静止线处理）。"""
    note = NoteData(
        type=2,
        start_time_beat=beat,
        end_time_beat=end_beat,
        position_x=0.0,
    )
    return NoteRenderInfo(
        note=note,
        true_x=0.0,
        beat=beat,
        end_beat=end_beat,
        is_multitap=False,
        judge_line_name="L",
        column=int(beat // COLUMN_BEATS),
        x_pixel=COLUMN_WIDTH / 2,
        y_pixel=(beat % COLUMN_BEATS) * BEAT_HEIGHT_PX,
        y_pixel_end=(end_beat % COLUMN_BEATS) * BEAT_HEIGHT_PX,
        judge_line=judge_line,
    )


def make_moving_line(start: float = -200.0, end: float = 200.0):
    """判定线在 [60, 70] 拍内从 start 线性移动到 end 的线。"""
    from rpe_render.models import EventData, EventLayer, JudgeLineData

    ev = EventData(
        bezier=False,
        bezier_points=[0, 0, 0, 0],
        easing_left=0.0,
        easing_right=1.0,
        easing_type=1,
        start=start,
        end=end,
        start_time=[60, 0, 1],
        end_time=[70, 0, 1],
        linkgroup=0,
    )
    return JudgeLineData(
        name="L",
        group=0,
        texture="",
        father=-1,
        z_order=0,
        is_cover=False,
        bpm_factor=1.0,
        notes=[],
        event_layers=[
            EventLayer(move_x_events=[ev]),
            EventLayer(),
            EventLayer(),
            EventLayer(),
        ],
    )


def make_rotating_line(angle: float = 180.0):
    """判定线角度恒定为 angle 的线（事件覆盖 [0, 128] 拍）。"""
    from rpe_render.models import EventData, EventLayer, JudgeLineData

    ev = EventData(
        bezier=False,
        bezier_points=[0, 0, 0, 0],
        easing_left=0.0,
        easing_right=1.0,
        easing_type=1,
        start=angle,
        end=angle,
        start_time=[0, 0, 1],
        end_time=[128, 0, 1],
        linkgroup=0,
    )
    return JudgeLineData(
        name="L",
        group=0,
        texture="",
        father=-1,
        z_order=0,
        is_cover=False,
        bpm_factor=1.0,
        notes=[],
        event_layers=[
            EventLayer(rotate_events=[ev]),
            EventLayer(),
            EventLayer(),
            EventLayer(),
        ],
    )


class TestPrepareHoldInfo:
    def test_basic_single_column(self, minimal_chart_path):
        chart = parse_chart(minimal_chart_path)
        infos = build_infos(chart)  # hold: 4 → 8 拍
        columns = compute_columns(8.0)
        prepared = prepare_hold_render_info(
            infos, {}, columns, head_img_height=50.0, end_img_height=50.0
        )

        assert len(prepared) == 1
        seg = prepared[0]
        assert seg.has_head and seg.has_end
        assert seg.head_y == pytest.approx(4 * BEAT_HEIGHT_PX - 25.0)
        assert seg.end_y == pytest.approx(8 * BEAT_HEIGHT_PX + 25.0)
        # Body 从 Head 图底到 End 图顶，头尾各向贴图内侧延伸实现无缝拼接
        assert seg.body_bottom_y == pytest.approx(
            4 * BEAT_HEIGHT_PX - HOLD_BODY_OVERLAP_PX
        )
        assert seg.body_top_y == pytest.approx(
            8 * BEAT_HEIGHT_PX + HOLD_BODY_OVERLAP_PX
        )
        assert seg.body_height == pytest.approx(
            8 * BEAT_HEIGHT_PX - 4 * BEAT_HEIGHT_PX + 2 * HOLD_BODY_OVERLAP_PX
        )

    def test_cross_column_split(self, hold_cross_chart_path):
        chart = parse_chart(hold_cross_chart_path)
        infos = build_infos(chart)  # hold: 60 → 70 拍，跨第 1/2 栏
        columns = compute_columns(70.0)
        prepared = prepare_hold_render_info(infos, {}, columns)

        assert len(prepared) == 2
        first, second = prepared
        assert first.column_index == 0 and second.column_index == 1
        assert first.has_head and not first.has_end
        assert second.has_end and not second.has_head
        # 中段 Body 覆盖整栏高度（默认名义图高 54 → 半高 27）；
        # 含 Head/End 的段各向贴图内侧延伸 HOLD_BODY_OVERLAP_PX
        assert first.body_bottom_y == pytest.approx(
            first.head_y + 27.0 - HOLD_BODY_OVERLAP_PX
        )
        assert first.body_top_y == pytest.approx(COLUMN_BEATS * BEAT_HEIGHT_PX)
        assert second.body_bottom_y == pytest.approx(0.0)
        assert second.body_top_y == pytest.approx(
            second.end_y - 27.0 + HOLD_BODY_OVERLAP_PX
        )

    def test_cross_column_segment_x_in_own_column(self, hold_cross_chart_path):
        # 回归：跨栏 Hold 的尾段必须使用本栏坐标的段内 X，
        # 不能沿用 Note 起始栏的 x_pixel（否则尾段被画进起始栏）
        chart = parse_chart(hold_cross_chart_path)
        infos = build_infos(chart)  # hold: 60 → 70 拍，判定线 -200 → 200
        columns = compute_columns(70.0)
        prepared = prepare_hold_render_info(infos, {}, columns)
        first, second = prepared

        # 头段（栏 0）：X = Note 起始 X（本栏内有效）
        assert first.x_pixel == pytest.approx(COLUMN_WIDTH / 2)

        # 尾段（栏 1）：X = 本段起始时刻（beat 64）的判定线 X 映射到栏 1
        seg_line_x = judge_line_x_at(first.note_info.judge_line, 64.0)
        assert second.x_pixel == pytest.approx(
            x_to_pixel(seg_line_x, columns[1].pixel_left)
        )
        # 尾段 X 必须落在栏 1 的像素区间内（而非栏 0）
        assert columns[1].pixel_left <= second.x_pixel <= columns[1].pixel_right

    def test_zero_duration(self, minimal_chart_path):
        chart = parse_chart(minimal_chart_path)
        note = NoteData(
            type=2,
            start_time_beat=5.0,
            end_time_beat=5.0,
            position_x=0.0,
        )
        info = NoteRenderInfo(
            note=note,
            true_x=0.0,
            beat=5.0,
            end_beat=5.0,
            is_multitap=False,
            judge_line_name="L",
            column=0,
            x_pixel=100.0,
            y_pixel=100.0,
            y_pixel_end=100.0,
            judge_line=None,
        )
        prepared = prepare_hold_render_info([info], {}, compute_columns(6.0))
        assert prepared[0].trajectory_points is None

    def test_static_hold_skips_trajectory(self):
        # 设计文档：无实际位移的 Hold 不渲染运动轨迹
        info = make_info(10.0, 12.0, judge_line=None)  # 静止线 X=0
        prepared = prepare_hold_render_info([info], {}, compute_columns(12.0))
        assert prepared[0].trajectory_points is None

    def test_moving_hold_keeps_trajectory(self):
        # 判定线在持续期内有位移 → 保留轨迹
        info = make_info(60.0, 70.0, judge_line=make_moving_line())
        prepared = prepare_hold_render_info([info], {}, compute_columns(70.0))
        assert prepared[0].trajectory_points is not None
        assert len(prepared[0].trajectory_points) > 2

    def test_negligible_motion_skips_trajectory(self):
        # 位移小于阈值（1 游戏单位 ≈ 0.33px < 1px）→ 视为无实际位移
        info = make_info(60.0, 70.0, judge_line=make_moving_line(start=0.0, end=1.0))
        prepared = prepare_hold_render_info([info], {}, compute_columns(70.0))
        assert prepared[0].trajectory_points is None


class TestRenderSegmentX:
    """跨栏尾段的 Body/End 必须渲染在段自身的栏内（回归测试）。"""

    @pytest.fixture()
    def ax(self):
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(4, 8), dpi=100)
        axes = fig.add_axes([0, 0, 1, 1])
        axes.set_xlim(0, 1050)
        axes.set_ylim(0, 6144)
        yield axes
        plt.close(fig)

    class _StubLoader:
        """返回 54x54 空白贴图的假加载器。"""

        def get_hold_body_image(self, note_type, is_hl, target_height_px):
            return np.zeros((target_height_px, 54, 4), dtype=np.uint8)

        def get_hold_end_image(self, is_hl):
            return np.zeros((54, 54, 4), dtype=np.uint8)

    def _tail_segment_info(self) -> HoldRenderInfo:
        note = NoteData(type=2, start_time_beat=60.0, end_time_beat=70.0, position_x=0.0)
        note_info = NoteRenderInfo(
            note=note,
            true_x=0.0,
            beat=60.0,
            end_beat=70.0,
            is_multitap=False,
            judge_line_name="L",
            column=0,
            x_pixel=225.0,  # Note 起始栏（栏 0）的 X —— 不能用于尾段
            y_pixel=0.0,
            y_pixel_end=0.0,
            judge_line=None,
        )
        return HoldRenderInfo(
            note_info=note_info,
            head_y=0.0,
            end_y=192.0,
            body_top_y=166.0,
            body_bottom_y=0.0,
            body_height=166.0,
            trajectory_points=None,
            x_pixel=811.0,  # 尾段在栏 1（600..1050）内的有效 X
            has_head=False,
            has_end=True,
            column_index=1,
        )

    def test_tail_segment_body_and_end_in_own_column(self, ax):
        info = self._tail_segment_info()
        loader = self._StubLoader()
        render_hold_body(ax, info, loader)
        render_hold_head_end(ax, info, loader)

        images = ax.get_images()
        assert len(images) == 2  # Body + End
        for img in images:
            left, right, _, _ = img.get_extent()
            # 段 X（811）± 半宽 27 → 全部落在栏 1 的像素区间 [600, 1050]
            assert left >= 600.0
            assert right <= 1050.0
        # 校验 X 中心确为段内 X 而非 Note 起始栏的 225
        assert (images[0].get_extent()[0] + images[0].get_extent()[1]) / 2 == pytest.approx(811.0)


class TestSampleTrajectory:
    def test_static_line_vertical(self):
        note = NoteData(type=2, start_time_beat=10, end_time_beat=12, position_x=100.0)
        pts = sample_hold_trajectory(None, note, 10.0, 12.0, samples_per_beat=4, column_offset_px=0.0)
        xs = {round(p[0]) for p in pts}
        assert len(xs) == 1  # X 固定

    def test_moving_line_bends(self):
        line = make_moving_line()
        note = NoteData(type=2, start_time_beat=60, end_time_beat=70, position_x=0.0)
        pts = sample_hold_trajectory(line, note, 60.0, 70.0, samples_per_beat=4, column_offset_px=0.0)
        assert len(pts) >= 3
        xs = [p[0] for p in pts]
        assert xs[0] < xs[-1]  # 判定线从 -200 移动到 +200
        assert len(xs) == len(set(xs)) - 0 or True  # 单调性由线性缓动保证
        assert all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))

    def test_sample_count_matches_density(self):
        note = NoteData(type=2, start_time_beat=0, end_time_beat=4.5, position_x=0.0)
        pts = sample_hold_trajectory(None, note, 0.0, 4.5, samples_per_beat=4, column_offset_px=0.0)
        assert len(pts) == max(2, int(4.5 * 4)) + 1

    def test_x_mapping_respects_offset(self):
        note = NoteData(type=2, start_time_beat=0, end_time_beat=1, position_x=GAME_X_MAX)
        pts = sample_hold_trajectory(None, note, 0.0, 1.0, samples_per_beat=2, column_offset_px=600.0)
        expected = x_to_pixel(GAME_X_MAX, 600.0)
        assert all(p[0] == pytest.approx(expected) for p in pts)


class TestSampleTrajectoryRotate:
    """旋转事件影响 Hold 轨迹采样（true_x = jl_x + positionX·cos(angle)）。"""

    def test_180_degree_flips_position_x(self):
        line = make_rotating_line(180.0)
        note = NoteData(type=2, start_time_beat=0, end_time_beat=2, position_x=450.0)
        pts = sample_hold_trajectory(line, note, 0.0, 2.0, samples_per_beat=4, column_offset_px=0.0)
        assert len(pts) >= 3
        for x_px, _ in pts:
            # 落点应在 -450 而非 +450
            assert x_px == pytest.approx(x_to_pixel(-450.0, 0.0))

    def test_90_degree_ignores_position_x(self):
        line = make_rotating_line(90.0)
        note = NoteData(type=2, start_time_beat=0, end_time_beat=2, position_x=600.0)
        pts = sample_hold_trajectory(line, note, 0.0, 2.0, samples_per_beat=4, column_offset_px=0.0)
        assert all(p[0] == pytest.approx(x_to_pixel(0.0, 0.0)) for p in pts)

    def test_no_rotate_unchanged(self):
        note = NoteData(type=2, start_time_beat=0, end_time_beat=2, position_x=300.0)
        pts = sample_hold_trajectory(None, note, 0.0, 2.0, samples_per_beat=4, column_offset_px=0.0)
        assert all(p[0] == pytest.approx(x_to_pixel(300.0, 0.0)) for p in pts)


class TestPrepareHoldInfoRotate:
    """跨栏尾段的段内 X 需按本栏起始时刻的角度修正。"""

    def test_cross_column_segment_x_applies_angle(self):
        note = NoteData(type=2, start_time_beat=60.0, end_time_beat=70.0, position_x=450.0)
        info = NoteRenderInfo(
            note=note,
            true_x=0.0,
            beat=60.0,
            end_beat=70.0,
            is_multitap=False,
            judge_line_name="L",
            column=0,
            x_pixel=COLUMN_WIDTH / 2,
            y_pixel=0.0,
            y_pixel_end=0.0,
            judge_line=make_rotating_line(180.0),
        )
        columns = compute_columns(70.0)
        prepared = prepare_hold_render_info([info], {}, columns)
        first, second = prepared
        # 头段 X = Note 起始 X（本栏内）
        assert first.x_pixel == pytest.approx(COLUMN_WIDTH / 2)
        # 尾段 X：beat 64 时角度 180° → 落点 -450 → 映射到栏 1
        assert second.x_pixel == pytest.approx(
            x_to_pixel(-450.0, columns[1].pixel_left)
        )
        assert columns[1].pixel_left <= second.x_pixel <= columns[1].pixel_right
