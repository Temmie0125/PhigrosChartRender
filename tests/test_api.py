"""Web API 渲染参数测试。"""

import pytest
from pydantic import ValidationError

from rpe_render.api import RenderOptions


def test_column_beats_defaults_to_auto():
    options = RenderOptions()
    assert options.smart_column_beats is True
    assert options.column_beats == 64


@pytest.mark.parametrize("value", [12, 18, 132])
def test_column_beats_rejects_invalid_value(value):
    with pytest.raises(ValidationError):
        RenderOptions(smart_column_beats=False, column_beats=value)
