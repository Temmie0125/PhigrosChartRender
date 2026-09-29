"""谱面左右镜像：将 Note 与判定线事件的横向坐标取反。

镜像语义与 Phigros 游戏内 Mirror 选项一致：
    - Note positionX 取反；
    - 判定线 moveX 事件值取反；
    - 判定线 rotate 事件角度取反：父线角度经由 sin 项进入子线的世界
      坐标，必须连同角度一起取反，子线位置才能得到几何上正确的镜像。
    - 事件值整体对 start/end 线性，取反两端即可让缓动插值在每个时刻
      同步镜像，贝塞尔缓动控制点描述进度映射、无需修改。
时间、Y 坐标与 alpha/speed 事件不受影响。
"""

from __future__ import annotations

from .models import ChartData


def mirror_chart(chart: ChartData) -> None:
    """原地左右镜像谱面配置（最终横向坐标取反）。"""
    for line in chart.judge_line_list:
        for layer in line.event_layers:
            for event in layer.move_x_events:
                event.start = -event.start
                event.end = -event.end
            for event in layer.rotate_events:
                event.start = -event.start
                event.end = -event.end
        for note in line.notes:
            note.position_x = -note.position_x


__all__ = ["mirror_chart"]
