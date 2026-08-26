"""自定义字体管理：加载配置的主字体并生成 FontProperties。

所有渲染文字统一通过 get_font(size) 获取字体属性：
- 主字体来自 constants.FONT_PATH（默认 resources/fonts/phi.ttf，可用 render_config.json 覆盖）；
- 字体文件缺失/损坏时回退到系统默认字体并发出警告（不阻断渲染）；
- 字体族列表末尾追加常见 CJK 字体族，主字体缺字（如信息栏中文）时按字形回退
  （matplotlib >= 3.6 支持跨字体族的逐字形回退）。
"""

from __future__ import annotations

import logging

import matplotlib
from matplotlib.font_manager import FontProperties

from . import constants

logger = logging.getLogger("rpe_render")

# 常见中文字体回退链（Windows / macOS / Linux）
_CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
)

# 已注册的自定义字体族名缓存；FONT_PATH 变化时自动失效（测试可重入）
_font_family: str | None = None
_font_path_seen: str = ""

# 本机可用的 CJK 回退字体族缓存（fontManager.ttflist 扫描一次后保持不变）
_available_cjk: tuple[str, ...] | None = None
# FontProperties 可安全复用；按字体族、回退链和字号缓存，避免每个
# Text artist 都重新触发 findfont 路径解析。
_font_cache: dict[tuple[str | None, tuple[str, ...], float], FontProperties] = {}


def _cjk_candidates() -> list[str]:
    """返回本机实际安装的 CJK 回退字体族。

    只保留 fontManager 中存在的候选，避免 matplotlib 对缺失字体族
    每次渲染都发出 findfont 警告。
    """
    global _available_cjk
    if _available_cjk is None:
        from matplotlib import font_manager

        available = {f.name for f in font_manager.fontManager.ttflist}
        _available_cjk = tuple(c for c in _CJK_FONT_CANDIDATES if c in available)
    return list(_available_cjk)


def _custom_font_family() -> str | None:
    """将 FONT_PATH 指定的字体注册到 fontManager，返回其族名。

    Returns:
        注册成功返回字体族名；文件不存在或加载失败返回 None。
    """
    global _font_family, _font_path_seen
    path = constants.FONT_PATH
    if not path:
        return None
    if path == _font_path_seen:
        return _font_family
    _font_path_seen = path
    _font_family = None

    from matplotlib import font_manager

    try:
        fp = FontProperties(fname=path)
        font_manager.fontManager.addfont(path)
        name = fp.get_name()
        logger.info("Loaded custom font %s (family %s)", path, name)
        _font_family = name
    except Exception as exc:  # noqa: BLE001 - 字体加载失败不应阻断渲染
        logger.warning(
            "Failed to load custom font %s (%s); falling back to default", path, exc
        )
        _font_family = None
    return _font_family


def get_font(size: float) -> FontProperties:
    """返回用于渲染文字的字号 fontproperties。

    Args:
        size: 字号（pt）

    Returns:
        FontProperties：优先使用配置的主字体（FONT_PATH），
        族名列表末尾追加常见 CJK 字体族用于缺字回退。
    """
    name = _custom_font_family()
    cjk = tuple(_cjk_candidates())
    key = (name, cjk, float(size))
    cached = _font_cache.get(key)
    if cached is not None:
        return cached
    family = [name, *cjk] if name else list(cjk)
    font = FontProperties(family=family, size=size)
    _font_cache[key] = font
    return font


def configure_cjk_font() -> None:
    """配置 matplotlib 全局字体设置（幂等）。

    与 get_font 搭配使用：get_font 负责逐字形回退，
    此处让未显式指定字体的文字（matplotlib 默认文本）也优先使用主字体，
    并修正负号在非 DejaVu 字体下的显示。
    """
    global _font_configured
    if _font_configured:
        return

    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    family: list[str] = []
    name = _custom_font_family()
    if name:
        family.append(name)
    family.extend(c for c in _CJK_FONT_CANDIDATES if c in available)
    if family:
        matplotlib.rcParams["font.sans-serif"] = family
    # 负号在非 DejaVu 字体下的显示修正
    matplotlib.rcParams["axes.unicode_minus"] = False
    _font_configured = True


_font_configured = False

__all__ = ["get_font", "configure_cjk_font"]
