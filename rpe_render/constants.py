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

# 拍线颜色与透明度（灰色；在深色轨道底色上清晰可见）
BEAT_LINE_COLOR: str = "#A8A8A8"
BEAT_LINE_ALPHA: float = 0.35
BEAT_LINE_WIDTH: float = 0.5

# 小节线颜色与透明度（每 4 拍，比拍线更亮一档以区分）
BAR_LINE_COLOR: str = "#D8D8D8"
BAR_LINE_ALPHA: float = 0.55
BAR_LINE_WIDTH: float = 1.2

# Hold 轨迹曲线
HOLD_TRAJECTORY_COLOR: str = "#AAAAAA"
HOLD_TRAJECTORY_WIDTH: float = 1.0

# 信息栏
INFO_BAR_TEXT_COLOR: str = "#FFFFFF"
# 信息栏高度（px）：为标题 + 5 行 Note 统计 + 四周统一边距（与左右约 29px 一致）预留空间
INFO_BAR_HEIGHT_PX: int = 320

# 信息栏标题颜色（Basic Information / Notes Info）
INFO_BAR_TITLE_COLOR: str = "#4CC3F8"

# 信息栏双边框：最外层为 0.75 透明度深灰色方框，间隔 8px 为内层圆角边框
INFO_BAR_BORDER_COLOR: str = "#4A4A4A"  # 深灰色
INFO_BAR_OUTER_BORDER_ALPHA: float = 0.75
INFO_BAR_BORDER_WIDTH_PX: float = 3.0
INFO_BAR_BORDER_GAP_PX: float = 8.0
INFO_BAR_ROUNDING_PX: float = 8.0

# 信息栏 Note 统计文本颜色（按 Note 类型区分）
NOTE_COLOR_TAP: str = "#44C0FE"
NOTE_COLOR_DRAG: str = "#EBEE6B"
NOTE_COLOR_HOLD: str = "#A1E5FC"
NOTE_COLOR_FLICK: str = "#F84566"

# 标记文字颜色（拍号/BPM/时值/计数）—— 白色，配合半透明黑色预览底色提高可读性
MARKER_TEXT_COLOR: str = "#FFFFFF"
BPM_TEXT_COLOR: str = "#FFFFFF"

# 谱面预览区半透明黑色底色透明度（0.0 = 关闭，1.0 = 不透明黑）
# 覆盖在曲绘背景之上、网格线之下，用于压暗背景突出白色标记文字与 Note
PREVIEW_BG_ALPHA: float = 0.55

# 每条 Note 轨道（分栏竖直区域，不含轨道间隔栏）的额外加深透明度（0.0 = 关闭）
# 在预览区底色之上再加深一档，提高相邻轨道之间的区分度
TRACK_BG_ALPHA: float = 0.75

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

# Hold Body 与 Head/End 贴图的重叠延伸量（px）
# Body 向两端各延伸该距离伸入 Head/End 贴图下方，消除精确对齐产生的接缝
# （与游戏内及主流谱面渲染器的 Hold 拼接方式一致）。
# 默认取 1px 的轻微重叠：足够覆盖抗锯齿接缝，又不会让 Hold 视觉上变长。
HOLD_BODY_OVERLAP_PX: float = 1.0

# 贴图目录（相对仓库根目录的默认值）
NOTES_DIR: str = "resources/notes"

# ==================== 自定义字体 ====================

# 主字体文件路径（相对仓库根目录或绝对路径）
# 所有渲染文字（拍号/BPM/时值间隔/累计计数/重合标注/信息栏）统一使用该字体；
# 文件缺失或加载失败时回退到系统默认字体并发出警告。
# 字体族列表末尾追加常见 CJK 字体族，主字体缺字（如信息栏中文）时按字形回退。
FONT_PATH: str = "resources/fonts/phi.ttf"

# ==================== 渲染质量控制 ====================

# 输出 DPI
OUTPUT_DPI: int = 150

# JPEG 输出质量（1~95）；较低质量可显著减小大谱面结果体积。
JPEG_QUALITY: int = 85

# 贝塞尔曲线插值密度
BEZIER_INTERPOLATION_DENSITY: int = 256

# Hold 轨迹曲线采样密度（每拍采样点数）
HOLD_TRAJECTORY_SAMPLES_PER_BEAT: int = 4

# Hold 轨迹渲染的最小位移阈值（像素 X 范围，px）
# 设计文档：仅当 Hold 持续期间存在实际位移时才渲染运动轨迹。
# 无位移时轨迹与竖直 Body 完全重合，渲染无意义，直接跳过。
HOLD_TRAJECTORY_MIN_DISPLACEMENT_PX: float = 1.0

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

# 拍号标记字号（pt）—— 栏左侧
BEAT_MARK_FONT_SIZE: float = 8.0

# BPM 变化标记字号（pt）—— 栏内最左侧
BPM_MARK_FONT_SIZE: float = 7.0

# 时值间隔 / 累计计数标记字号（pt）—— 栏内右缘 / 栏外右侧
COUNT_MARK_FONT_SIZE: float = 7.0

# ==================== Note 开始时间重合标注 ====================

# 实验性官谱分音拟合（默认关闭，可能改变 Note 的实际开始位置）。
FIT_OFFICIAL_DIVISIONS: bool = False

# 同一时刻、同一位置且几何完全一致的重复 Note 最多实际绘制数量。
# 仅用于防御完全重复的 Note 炸弹；数量统计与旁侧重合标注不受影响。
NOTE_BOMB_RENDER_LIMIT: int = 4

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

# ==================== 受影响段（近竖直判定线）渲染 ====================

# 判定线角度（度）在 [±AFFECTED_ANGLE_MIN_DEG, ±AFFECTED_ANGLE_MAX_DEG] 之间时
# 视为"接近竖直"：note 落点压缩在判定线附近，几乎看不出水平走向。
# 对这类段在主栏绘制圆角白框提示，并在受影响栏右侧的小区域中渲染水平分布。
AFFECTED_ANGLE_MIN_DEG: float = 75.0  # |角度| 下限（含）
AFFECTED_ANGLE_MAX_DEG: float = 90.0  # |角度| 上限（含）

# 受影响栏右侧额外间距（为小区域预留画布空间的最小值）（px）
# 小区域宽度随谱面动态变化（受影响 note 的真实横向占用宽度，
# 见 affected_area_renderer.compute_affected_area_widths），实际间距取
# max(本值, MARGIN_LEFT + 区域宽度)，保证小区域不被右侧栏或画布右缘遮挡。
AFFECTED_AREA_EXTRA_GAP_PX: float = 150.0

# 小区域左缘相对栏右缘的偏移（避开计数标记 20px + 7pt 文字，
# 并预留约 20px 余量，避免多位数计数文字进入小区域）（px）
AFFECTED_AREA_MARGIN_LEFT_PX: float = 64.0

# 小区域边框（底色与主栏轨道一致，不单独填充）
AFFECTED_AREA_BORDER_COLOR: str = "#CCCCCC"

# 圆角白框描边（空心，不填充）
AFFECTED_BOX_EDGE_COLOR: str = "#FFFFFF"

# 白框内相邻受影响 note 的最大间隔（拍）：间隔超过该值时拆分为独立白框，
# 避免无 note 的长段被超长白框框出；同一栏内发生重合的白框会合并为一个大框。
AFFECTED_BOX_CLUSTER_GAP_BEATS: float = 8.0

# 白框横向边距（图标半宽之外）/ 纵向边距（px）
AFFECTED_BOX_PAD_X_PX: float = 6.0
AFFECTED_BOX_PAD_Y_PX: float = 6.0

# 白框圆角半径（px）
AFFECTED_BOX_ROUNDING_PX: float = 8.0

# ==================== 配置文件覆盖 ====================

import os
import warnings
from pathlib import Path

# 配置文件机制：默认读取当前工作目录下的 render_config.json，
# 也可通过环境变量 RPE_RENDER_CONFIG 指定路径，或调用 load_config(path) 手动加载。
# 文件中每个键对应本模块的一个常量名（大小写不敏感），值将覆盖默认值；
# 未知键、类型不匹配的键会被忽略并发出警告；以 "_" 开头的键视为注释。
# 这样无需修改代码即可自由调整渲染参数；tests 假定默认配置（不创建配置文件）。
CONFIG_FILE_NAME: str = "render_config.json"
CONFIG_ENV_VAR: str = "RPE_RENDER_CONFIG"

# 配置机制自身的名字，不允许被配置文件覆盖
_CONFIG_INTERNAL_KEYS = frozenset(
    {"load_config", "CONFIG_FILE_NAME", "CONFIG_ENV_VAR"}
)


def load_config(path: str | Path | None = None) -> dict[str, object]:
    """从 JSON 配置文件加载覆盖值并应用到本模块常量。

    Args:
        path: 配置文件路径；None 时优先使用环境变量 RPE_RENDER_CONFIG，
            未设置则读取当前目录下的 render_config.json。

    Returns:
        实际应用的 {常量名: 新值} 字典（无配置文件或文件无效时为空）。
    """
    if path is None:
        path = os.environ.get(CONFIG_ENV_VAR, CONFIG_FILE_NAME)
    path = Path(path)
    if not path.is_file():
        return {}

    import json

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        warnings.warn(f"忽略配置文件 {path}: {exc}", stacklevel=2)
        return {}

    if not isinstance(data, dict):
        warnings.warn(f"忽略配置文件 {path}: 顶层必须是 JSON 对象", stacklevel=2)
        return {}

    mod = globals()
    applied: dict[str, object] = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue  # 下划线开头视为注释，不生效也不告警
        target = key
        if target not in mod or target in _CONFIG_INTERNAL_KEYS:
            target = key.upper()
        if (
            target not in mod
            or target in _CONFIG_INTERNAL_KEYS
            or not target.isupper()
            or callable(mod[target])
        ):
            warnings.warn(
                f"配置文件 {path}: 忽略未知配置项 '{key}'", stacklevel=2
            )
            continue
        expected_type = type(mod[target])
        if not isinstance(value, expected_type):
            warnings.warn(
                f"配置文件 {path}: 配置项 '{key}' 类型应为 "
                f"{expected_type.__name__}，忽略 '{value!r}'",
                stacklevel=2,
            )
            continue
        mod[target] = value
        applied[target] = value
    return applied


load_config()  # 模块导入时应用环境变量 / 默认配置文件中的覆盖
