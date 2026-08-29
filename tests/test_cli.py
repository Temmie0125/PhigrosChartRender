"""命令行参数解析测试。"""

import pytest

from rpe_render.cli import parse_args


def test_column_beats_auto():
    config = parse_args(["chart.json", "--column-beats", "auto"])
    assert config.smart_column_beats is True


def test_column_beats_custom():
    config = parse_args(["chart.json", "--column-beats", "48"])
    assert config.smart_column_beats is False
    assert config.column_beats == 48


@pytest.mark.parametrize("value", ["12", "18", "132", "invalid"])
def test_column_beats_rejects_invalid_value(value):
    with pytest.raises(SystemExit):
        parse_args(["chart.json", "--column-beats", value])
