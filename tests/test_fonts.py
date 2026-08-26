"""自定义字体模块测试：主字体加载、缺失回退与全局配置。"""

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import pytest

from rpe_render import constants, fonts

logger = logging.getLogger("rpe_render")


def _real_font_path() -> str:
    """返回一个必定存在的字体文件（matplotlib 自带 DejaVu Sans）。"""
    from matplotlib import font_manager

    return font_manager.findfont("DejaVu Sans")


class TestGetFont:
    def test_reuses_properties_for_same_size(self):
        assert fonts.get_font(8.0) is fonts.get_font(8.0)

    def test_default_font_path_points_to_existing_file(self, project_root):
        # 仓库默认主字体必须存在，否则所有文字静默回退
        assert Path(constants.FONT_PATH).is_file()

    def test_uses_configured_font_when_present(self, monkeypatch):
        monkeypatch.setattr(constants, "FONT_PATH", _real_font_path())
        fp = fonts.get_font(12.0)
        assert fp.get_size() == 12.0
        # 族名列表首位为配置字体自身的族名（来自字体文件的 name 表），
        # 末尾追加本机可用的 CJK 回退链
        assert fp.get_family() == ["DejaVu Sans", *fonts._cjk_candidates()]

    def test_falls_back_when_font_missing(self, monkeypatch, caplog):
        monkeypatch.setattr(
            constants, "FONT_PATH", str(Path("no/such/dir/phi.ttf"))
        )
        with caplog.at_level(logging.WARNING, logger="rpe_render"):
            fp = fonts.get_font(10.0)
        # 不抛异常，回退到本机可用的 CJK 候选族名（不含自定义字体名）
        assert fp.get_size() == 10.0
        assert fp.get_family() == fonts._cjk_candidates()
        assert any(
            record.levelno >= logging.WARNING
            and "Failed to load custom font" in record.getMessage()
            for record in caplog.records
        )

    def test_cache_invalidates_on_font_path_change(self, monkeypatch):
        # 先加载有效字体，再改为缺失路径：缓存必须失效并回退
        monkeypatch.setattr(constants, "FONT_PATH", _real_font_path())
        first = fonts.get_font(10.0)
        assert first.get_family()[0] == "DejaVu Sans"

        monkeypatch.setattr(constants, "FONT_PATH", "no/such/font.ttf")
        second = fonts.get_font(10.0)
        assert "DejaVu Sans" not in second.get_family()

    def test_empty_font_path_uses_fallback(self, monkeypatch):
        monkeypatch.setattr(constants, "FONT_PATH", "")
        fp = fonts.get_font(8.0)
        assert fp.get_family() == fonts._cjk_candidates()


class TestConfigureCjkFont:
    def test_configures_rcparams_with_custom_font(self, monkeypatch):
        monkeypatch.setattr(constants, "FONT_PATH", _real_font_path())
        fonts._font_configured = False  # 重置幂等标志以便重跑
        fonts.configure_cjk_font()
        assert matplotlib.rcParams["font.sans-serif"][0] == "DejaVu Sans"
        assert matplotlib.rcParams["axes.unicode_minus"] is False

    def test_idempotent(self, monkeypatch):
        monkeypatch.setattr(constants, "FONT_PATH", _real_font_path())
        fonts._font_configured = False
        fonts.configure_cjk_font()
        fonts.configure_cjk_font()  # 不抛异常即可
