"""三次贝塞尔曲线缓动，移植自 TypeScript 版 BezierEasing 类。

使用 256 段折线近似 + 跳跃数组加速查找。
"""

from __future__ import annotations

import math

from ..constants import BEZIER_INTERPOLATION_DENSITY

TupleCoord = tuple[float, float]

# 插值步长
_BEZIER_INTERPOLATION_STEP = 1 / BEZIER_INTERPOLATION_DENSITY


class BezierEasing:
    """三次贝塞尔曲线缓动（不可变对象）。

    Attributes:
        cp1: 控制点 1 (x1, y1)
        cp2: 控制点 2 (x2, y2)
    """

    def __init__(self, cp1: TupleCoord, cp2: TupleCoord):
        """初始化时对贝塞尔参数方程采样，构建折线近似与跳跃数组。

        Args:
            cp1: 控制点 1 (x1, y1), x1 ∈ [0, 1]
            cp2: 控制点 2 (x2, y2), x2 ∈ [0, 1]
        """
        self.cp1 = cp1
        self.cp2 = cp2

        # 插值，把贝塞尔曲线近似成 N 段折线（不含端点 t=0 与 t=1）
        xs: list[float] = []
        ys: list[float] = []

        # 跳跃数组：刻度 i * step -> xs 中第一个 x >= 该刻度的采样点下标
        jumper = [-1] * BEZIER_INTERPOLATION_DENSITY
        next_to_fill = 0

        for i in range(1, BEZIER_INTERPOLATION_DENSITY):
            # 这个 t 是贝塞尔曲线生成参数
            t = i * _BEZIER_INTERPOLATION_STEP
            s = 1 - t
            x = (
                3 * cp1[0] * math.pow(s, 2) * t
                + 3 * cp2[0] * math.pow(t, 2) * s
                + math.pow(t, 3)
            )
            y = (
                3 * cp1[1] * math.pow(s, 2) * t
                + 3 * cp2[1] * math.pow(t, 2) * s
                + math.pow(t, 3)
            )
            xs.append(x)
            ys.append(y)
            while x > next_to_fill * _BEZIER_INTERPOLATION_STEP and next_to_fill < BEZIER_INTERPOLATION_DENSITY:
                jumper[next_to_fill] = i - 1
                next_to_fill += 1

        self.xs = xs
        self.ys = ys
        self.jumper = jumper

    def get_value(self, t: float) -> float:
        """从横坐标 t 获取对应的纵坐标值。

        Args:
            t: 横坐标 ∈ [0, 1]（不是贝塞尔参数，是已映射到 x 轴的位置）

        Returns:
            对应的 y 值 ∈ [0, 1]
        """
        if t == 0 or t == 1:
            return t

        index = self.jumper[int(math.floor(t * BEZIER_INTERPOLATION_DENSITY))]
        # jumper 中未被填充的槽位（x 值超过最后一个采样点的情况）
        if index < 0:
            index = len(self.xs) - 1

        xs = self.xs
        ys = self.ys
        n = len(xs)

        next_val = -1.0
        while index < n - 1:
            next_val = xs[index + 1]
            if t < next_val:
                break
            index += 1

        at_last_segment = index == n - 1
        here = 1 if at_last_segment else xs[index]
        y_here = 1 if at_last_segment else ys[index]
        y_prev = ys[index - 1] if index > 0 else 0
        x_prev = xs[index - 1] if index > 0 else 0

        denom = x_prev - here
        if denom == 0:
            return y_here
        k = (y_prev - y_here) / denom
        return k * (t - here) + y_here
