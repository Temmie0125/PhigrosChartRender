"""easing/bezier 单元测试。"""

import math

import pytest

from rpe_render.easing.bezier import BezierEasing


class TestBezierEasing:
    def test_endpoints(self):
        curve = BezierEasing((0.25, 0.1), (0.25, 1.0))  # CSS ease 曲线
        assert curve.get_value(0.0) == 0.0
        assert curve.get_value(1.0) == 1.0

    def test_monotonic_x_sampling(self):
        curve = BezierEasing((0.25, 0.1), (0.25, 1.0))
        xs = curve.xs
        assert all(xs[i] < xs[i + 1] for i in range(len(xs) - 1))

    def test_interpolation_continuity(self):
        curve = BezierEasing((0.25, 0.1), (0.25, 1.0))
        prev = curve.get_value(0.01)
        for i in range(2, 100):
            t = i / 100
            cur = curve.get_value(t)
            # 相邻采样变化幅度有限（连续性）
            assert abs(cur - prev) < 0.05
            prev = cur

    def test_symmetric_curve_center_is_half(self):
        # 控制点中心对称时 f(0.5) ≈ 0.5
        curve = BezierEasing((0.25, 0.25), (0.75, 0.75))
        assert curve.get_value(0.5) == pytest.approx(0.5, abs=0.02)

    def test_linear_control_points(self):
        # 控制点在对角线上 → 接近线性
        curve = BezierEasing((0.0, 0.0), (1.0, 1.0))
        for t in (0.2, 0.4, 0.6, 0.8):
            assert curve.get_value(t) == pytest.approx(t, abs=0.01)

    def test_jumper_filled(self):
        curve = BezierEasing((0.33, 0.0), (0.67, 1.0))
        # jumper 覆盖所有刻度槽位（未填满的为 -1，仅在 x 未达末尾时出现）
        assert len(curve.jumper) == 256
        assert any(v >= 0 for v in curve.jumper)
