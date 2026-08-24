"""集中管理所有可调渲染参数。本模块不包含任何业务逻辑。"""

# ==================== 画布与布局 ====================

# 每拍像素高度
BEAT_HEIGHT_PX: int = 96

# 每栏拍数（16 小节 = 64 拍）
COLUMN_BEATS: int = 64

# 单栏渲染宽度（px）
COLUMN_WIDTH: int = 450

# 栏间距（为左右标记文字留空间）（px）
COLUMN_GAP: int = 150

# 画布左右两侧预留的标记文字空间（px）
# 首栏左侧的拍号/BPM 标记与末栏右侧的计数标记需要超出栏边界绘制，
# 此边距计入画布尺寸，保证文字不被裁剪。
SIDE_MARKER_PADDING_PX: float = 64.0

# ==================== 坐标映射 ====================

# 游戏画面 X 坐标范围
GAME_X_MIN: float = -675.0
GAME_X_MAX: float = 675.0

# Note 图标渲染宽度（px）
NOTE_ICON_WIDTH: int = 54

# ==================== 颜色与样式 ====================

# 背景色
BG_COLOR: str = "#FAFAFA"

# 拍线颜色与透明度
BEAT_LINE_COLOR: str = "#000000"
BEAT_LINE_ALPHA: float = 0.18
BEAT_LINE_WIDTH: float = 0.5

# 小节线颜色与透明度（每 4 拍）
BAR_LINE_COLOR: str = "#000000"
BAR_LINE_ALPHA: float = 0.36
BAR_LINE_WIDTH: float = 1.2

# Hold 轨迹曲线
HOLD_TRAJECTORY_COLOR: str = "#AAAAAA"
HOLD_TRAJECTORY_WIDTH: float = 1.0

# 信息栏
INFO_BAR_BG_COLOR: str = "#F0F0F0"
INFO_BAR_TEXT_COLOR: str = "#333333"
INFO_BAR_HEIGHT_PX: int = 280

# 标记文字颜色（拍号/BPM/时值/计数）—— 白色，配合半透明黑色预览底色提高可读性
MARKER_TEXT_COLOR: str = "#FFFFFF"
BPM_TEXT_COLOR: str = "#FFFFFF"

# 谱面预览区半透明黑色底色透明度（0.0 = 关闭，1.0 = 不透明黑）
# 覆盖在曲绘背景之上、网格线之下，用于压暗背景突出白色标记文字与 Note
PREVIEW_BG_ALPHA: float = 0.55

# 栏外侧文字边距（px）
MARKER_MARGIN_PX: float = 20.0

# BPM 标记在栏内左侧的内缩距离（px）
# 写在栏内最左侧，避免与栏外左缘的拍号标记重合
BPM_MARK_INSET_PX: float = 8.0

# ==================== 贴图路径 ====================

# Note 贴图文件名映射: type -> (normal, highlight)
NOTE_IMAGE_MAP: dict[int, tuple[str, str]] = {
    1: ("Tap.png", "TapHL.png"),  # Tap
    2: ("HoldHead.png", "HoldHeadHL.png"),  # Hold (仅 Head 使用此映射)
    3: ("Flick.png", "FlickHL.png"),  # Flick
    4: ("Drag.png", "DragHL.png"),  # Drag
}

# Hold 特定贴图
HOLD_BODY_IMAGE: str = "Hold.png"
HOLD_BODY_HL_IMAGE: str = "HoldHL.png"
HOLD_END_IMAGE: str = "HoldEnd.png"
HOLD_END_HL_IMAGE: str = "HoldEndHL.png"

# 贴图目录（相对仓库根目录的默认值）
NOTES_DIR: str = "resources/notes"

# ==================== 渲染质量控制 ====================

# 输出 DPI
OUTPUT_DPI: int = 150

# 贝塞尔曲线插值密度
BEZIER_INTERPOLATION_DENSITY: int = 256

# Hold 轨迹曲线采样密度（每拍采样点数）
HOLD_TRAJECTORY_SAMPLES_PER_BEAT: int = 4

# ==================== 标记规则 ====================

# 拍号标记间隔（拍）
BEAT_MARK_INTERVAL: int = 4

# 小节线间隔（拍）
BAR_LINE_INTERVAL: int = 4

# 时值间隔标记的最大间隔（拍）
# 仅标记间隔 <= 1/4 拍（16 分音符）的相邻 Tap/Hold
MAX_INTERVAL_MARK_BEAT: float = 0.25

# 累计计数标记间隔（拍）
COUNT_MARK_INTERVAL: int = 4

# ==================== Note 开始时间重合标注 ====================

# 重合判定阈值（谱面原始 X 距离，游戏坐标单位）：同一开始时间的 Note 中，
# 原始 X 距离 <= 阈值视为视觉重合；Hold 仅以头部参与判定
NOTE_OVERLAP_THRESHOLD_X: float = 75.0

# "×n" 标注相对组最右 Note 的横向偏移（px），写在 Note 旁边（栏内）
NOTE_OVERLAP_LABEL_OFFSET_PX: float = 14.0

# ==================== 背景处理 ====================

# 曲绘高斯模糊 σ
BACKGROUND_BLUR_SIGMA: float = 15.0

# 曲绘亮度系数（1.0 为原始亮度）
BACKGROUND_BRIGHTNESS: float = 0.75
