"""constants 配置文件覆盖机制测试。"""

import json
import warnings
from pathlib import Path

import pytest

from rpe_render import constants


@pytest.fixture()
def restored_constants():
    """每个用例后恢复 constants 模块的全部全局状态。"""
    snapshot = dict(constants.__dict__)
    yield
    constants.__dict__.clear()
    constants.__dict__.update(snapshot)


def write_config(tmp_path, data, name="render_config.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestLoadConfig:
    def test_applies_overrides(self, restored_constants, tmp_path):
        p = write_config(
            tmp_path,
            {"BEAT_HEIGHT_PX": 128, "TRACK_BG_ALPHA": 0.5},
        )
        applied = constants.load_config(p)
        assert constants.BEAT_HEIGHT_PX == 128
        assert constants.TRACK_BG_ALPHA == 0.5
        assert applied == {"BEAT_HEIGHT_PX": 128, "TRACK_BG_ALPHA": 0.5}

    def test_smart_column_beats_override(self, restored_constants, tmp_path):
        p = write_config(tmp_path, {"SMART_COLUMN_BEATS": False})
        applied = constants.load_config(p)
        assert constants.SMART_COLUMN_BEATS is False
        assert applied == {"SMART_COLUMN_BEATS": False}

    def test_lowercase_key_matches(self, restored_constants, tmp_path):
        p = write_config(tmp_path, {"beat_height_px": 64})
        constants.load_config(p)
        assert constants.BEAT_HEIGHT_PX == 64

    def test_unknown_key_warns_and_ignored(self, restored_constants, tmp_path):
        p = write_config(tmp_path, {"NOT_A_CONSTANT": 1, "BEAT_HEIGHT_PX": 96})
        with pytest.warns(UserWarning):
            constants.load_config(p)
        assert not hasattr(constants, "NOT_A_CONSTANT")

    def test_type_mismatch_ignored(self, restored_constants, tmp_path):
        before = constants.BEAT_HEIGHT_PX
        p = write_config(tmp_path, {"BEAT_HEIGHT_PX": "many"})
        with pytest.warns(UserWarning):
            constants.load_config(p)
        assert constants.BEAT_HEIGHT_PX == before

    def test_underscore_keys_ignored_silently(self, restored_constants, tmp_path):
        p = write_config(tmp_path, {"_comment": "hello", "BEAT_HEIGHT_PX": 120})
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # 任何警告都会使测试失败
            constants.load_config(p)
        assert constants.BEAT_HEIGHT_PX == 120

    def test_missing_file_returns_empty(self, restored_constants, tmp_path):
        assert constants.load_config(tmp_path / "nope.json") == {}

    def test_no_config_in_cwd_no_warning(self, restored_constants, tmp_path, monkeypatch):
        # 当前目录无配置文件时 load_config() 为空操作且不告警
        monkeypatch.chdir(tmp_path)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert constants.load_config() == {}

    def test_invalid_json_warns(self, restored_constants, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{oops", encoding="utf-8")
        with pytest.warns(UserWarning):
            assert constants.load_config(p) == {}

    def test_non_dict_top_level_warns(self, restored_constants, tmp_path):
        p = write_config(tmp_path, [1, 2])
        with pytest.warns(UserWarning):
            assert constants.load_config(p) == {}

    def test_env_var_path_used(self, restored_constants, tmp_path, monkeypatch):
        p = write_config(tmp_path, {"BEAT_HEIGHT_PX": 200})
        monkeypatch.setenv(constants.CONFIG_ENV_VAR, str(p))
        applied = constants.load_config()  # path=None → 读取环境变量路径
        assert constants.BEAT_HEIGHT_PX == 200
        assert applied == {"BEAT_HEIGHT_PX": 200}

    def test_explicit_path_beats_env(self, restored_constants, tmp_path, monkeypatch):
        p_env = write_config(tmp_path, {"BEAT_HEIGHT_PX": 300}, name="env.json")
        p_explicit = write_config(tmp_path, {"BEAT_HEIGHT_PX": 400}, name="explicit.json")
        monkeypatch.setenv(constants.CONFIG_ENV_VAR, str(p_env))
        constants.load_config(p_explicit)
        assert constants.BEAT_HEIGHT_PX == 400

    def test_config_mechanics_not_overridable(self, restored_constants, tmp_path):
        before = constants.CONFIG_FILE_NAME
        p = write_config(tmp_path, {"CONFIG_FILE_NAME": "evil.json"})
        with pytest.warns(UserWarning):
            constants.load_config(p)
        assert constants.CONFIG_FILE_NAME == before


class TestExampleConfigSync:
    """示例配置文件的每个键必须与 constants 默认值一致，防止两边漂移。"""

    def test_example_config_matches_defaults(self):
        example_path = (
            Path(__file__).resolve().parent.parent / "render_config.example.json"
        )
        data = json.loads(example_path.read_text(encoding="utf-8"))
        mismatched = {}
        for key, value in data.items():
            if key.startswith("_"):
                continue  # 注释键不参与校验
            assert hasattr(constants, key), f"示例配置含未知键: {key}"
            if getattr(constants, key) != value:
                mismatched[key] = (getattr(constants, key), value)
        assert not mismatched, (
            "constants 默认值与 render_config.example.json 不一致"
            f"（常量值, 示例值）: {mismatched}"
        )
