"""谱面与渲染中间数据的模型定义。

数据类集中在本模块，使计算层各模块（chart_parser / easing / timeline）
可以独立引用而不产生循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ==================== 谱面数据类 ====================

@dataclass
class BPMEvent:
    """BPM 变化事件"""

    bpm: float
    start_time: list[int]  # TimeT, 保留原始格式供 time_utils 转换
    # 注: endTime 由下一个 BPMEvent 的 startTime 隐式定义


@dataclass
class MetaData:
    """谱面元信息"""

    rpe_version: int
    background: str
    charter: str
    composer: str
    chart_id: str
    level: str
    name: str
    offset: int
    song: str
    illustration: str = ""  # 可选，曲绘画师
    duration: float = 0.0  # 可选，谱面时长（秒）


@dataclass
class EventData:
    """RPE 事件数据（moveX/moveY/rotate/alpha/speed 统一结构）"""

    bezier: bool  # 是否使用贝塞尔缓动
    bezier_points: list[float]  # [x1, y1, x2, y2] 四个贝塞尔控制点坐标
    easing_left: float  # 缓动左截取边界 [0, 1]
    easing_right: float  # 缓动右截取边界 [0, 1]
    easing_type: int  # 缓动类型编号 1-29
    start: float  # 起始值
    end: float  # 结束值
    start_time: list[int]  # TimeT
    end_time: list[int]  # TimeT
    linkgroup: int  # 链接组（暂不使用）


@dataclass
class EventLayer:
    """判定线的一个事件层级"""

    move_x_events: list[EventData] = field(default_factory=list)
    move_y_events: list[EventData] = field(default_factory=list)
    rotate_events: list[EventData] = field(default_factory=list)
    alpha_events: list[EventData] = field(default_factory=list)
    speed_events: list[EventData] = field(default_factory=list)


@dataclass
class NoteData:
    """音符数据（已解析为拍数）"""

    type: int  # 1=Tap, 2=Hold, 3=Flick, 4=Drag
    start_time_beat: float  # startTime 转换为拍数
    end_time_beat: float  # endTime 转换为拍数
    position_x: float  # 相对于判定线的 X 落点
    raw_start_time: list[int] = field(default_factory=list)  # 原始 TimeT，用于多押精确比较
    raw_end_time: list[int] = field(default_factory=list)


@dataclass
class JudgeLineData:
    """判定线数据（已解析）"""

    name: str
    group: int
    texture: str
    father: int  # 父线 ID，-1 表示无父线
    z_order: int
    is_cover: bool
    bpm_factor: float
    notes: list[NoteData]
    event_layers: list[EventLayer]  # 固定 4 个层级


@dataclass
class ChartData:
    """完整的谱面数据（已解析）"""

    bpm_list: list[BPMEvent]
    meta: MetaData
    judge_line_group: list[str]
    judge_line_list: list[JudgeLineData]


# ==================== 渲染中间数据类 ====================

@dataclass
class NoteRenderInfo:
    """单个音符的渲染信息"""

    note: NoteData  # 原始音符数据引用
    true_x: float  # 游戏画面真实 X 坐标
    beat: float  # startTime 拍数
    end_beat: float  # endTime 拍数（仅 Hold 有效）
    is_multitap: bool  # 是否属于多押
    judge_line_name: str  # 来源判定线名称（调试用）
    column: int  # 所在分栏索引
    x_pixel: float  # 像素 X 坐标
    y_pixel: float  # 像素 Y 坐标（startTime）
    y_pixel_end: float  # 像素 Y 坐标（endTime，仅 Hold 有效）
    judge_line: object | None = None  # 来源判定线引用（供 Hold 轨迹采样）
    line_angle: float = 0.0  # note startTime 时判定线角度（度，4 层 rotateEvents 叠加）


@dataclass
class ColumnInfo:
    """分栏信息"""

    index: int  # 栏索引
    beat_start: float  # 该栏起始拍数
    beat_end: float  # 该栏结束拍数
    pixel_left: float  # 栏左侧像素 X
    pixel_right: float  # 栏右侧像素 X
    pixel_bottom: float  # 栏底部像素 Y
    pixel_top: float  # 栏顶部像素 Y
    pixel_gap_right: float = 0.0  # 该栏右侧额外间距（受影响栏 > 0，其余 0）


@dataclass
class NoteCountStats:
    """Note 统计信息"""

    tap: int = 0
    hold: int = 0
    flick: int = 0
    drag: int = 0

    @property
    def total(self) -> int:
        return self.tap + self.hold + self.flick + self.drag
