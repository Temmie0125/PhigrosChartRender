"""easing/functions 单元测试：29 种缓动 + 映射表。"""

import math

import pytest

from rpe_render.easing.functions import (
    EASING_FUNCTIONS,
    EASING_TYPE_TO_NAME,
    get_easing_by_name,
    get_easing_by_type,
)

EXPECTED_NAMES = {
    "linear", "easeInSine", "easeOutSine", "easeInOutSine",
    "easeInQuad", "easeOutQuad", "easeInOutQuad",
    "easeInCubic", "easeOutCubic", "easeInOutCubic",
    "easeInQuart", "easeOutQuart", "easeInOutQuart",
    "easeInQuint", "easeOutQuint", "easeInOutQuint",
    "easeInExpo", "easeOutExpo", "easeInOutExpo",
    "easeInCirc", "easeOutCirc", "easeInOutCirc",
    "easeInBack", "easeOutBack", "easeInOutBack",
    "easeInElastic", "easeOutElastic", "easeInOutElastic",
    "easeInBounce", "easeOutBounce", "easeInOutBounce",
}


class TestMapping:
    def test_all_29_types_present(self):
        assert set(EASING_TYPE_TO_NAME.keys()) == set(range(1, 30))

    def test_functions_dict_complete(self):
        assert EXPECTED_NAMES.issubset(EASING_FUNCTIONS.keys())

    def test_get_easing_by_type_valid(self):
        for t in range(1, 30):
            fn = get_easing_by_type(t)
            assert callable(fn)
            # 与名称映射一致
            assert fn is get_easing_by_name(EASING_TYPE_TO_NAME[t])

    def test_get_easing_by_type_invalid(self):
        for bad in (0, 30, -1):
            with pytest.raises(KeyError):
                get_easing_by_type(bad)


class TestEndpoints:
    """对每种缓动函数测试 f(0) == 0, f(1) == 1（Back/Elastic 类允许中间越界）。"""

    SAMPLE_POINTS = (0.25, 0.5, 0.75)

    def test_all_endpoints(self):
        for name, fn in EASING_FUNCTIONS.items():
            assert fn(0.0) == pytest.approx(0.0, abs=1e-9), name
            assert fn(1.0) == pytest.approx(1.0, abs=1e-9), name


class TestKnownValues:
    """与 TypeScript 版输出一致的抽查值。"""

    def test_linear(self):
        assert get_easing_by_name("linear")(0.3) == 0.3

    def test_sine(self):
        assert get_easing_by_name("easeOutSine")(0.5) == pytest.approx(
            math.sin(math.pi / 4)
        )
        assert get_easing_by_name("easeInSine")(0.5) == pytest.approx(
            1 - math.cos(math.pi / 4)
        )

    def test_quad(self):
        assert get_easing_by_name("easeInQuad")(0.5) == 0.25
        assert get_easing_by_name("easeOutQuad")(0.5) == 0.75
        assert get_easing_by_name("easeInOutQuad")(0.25) == pytest.approx(0.125)
        assert get_easing_by_name("easeInOutQuad")(0.75) == pytest.approx(0.875)

    def test_expo_boundaries(self):
        fn_in = get_easing_by_name("easeInExpo")
        fn_out = get_easing_by_name("easeOutExpo")
        assert fn_in(0.0) == 0
        assert fn_out(1.0) == 1
        assert fn_in(0.5) == pytest.approx(2**-5)
        assert fn_out(0.5) == pytest.approx(1 - 2**-5)

    def test_bounce_structure(self):
        fn = get_easing_by_name("easeOutBounce")
        # 第一段分支（x < 1/2.75）：n1 * x^2
        assert fn(0.25) == pytest.approx(7.5625 * 0.25**2)
        # 终点精确为 1
        assert fn(1.0) == pytest.approx(1.0)
