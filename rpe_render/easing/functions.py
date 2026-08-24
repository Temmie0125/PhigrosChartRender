"""29 种缓动函数，精确移植自 TypeScript 版 easingsFunctions.ts。

所有函数输入 t ∈ [0, 1]，输出 ∈ [0, 1]。
"""

from __future__ import annotations

import math
from typing import Callable

# 缓动函数签名：输入 t ∈ [0, 1]，输出 ∈ [0, 1]
EasingFunction = Callable[[float], float]

_pow = math.pow
_sqrt = math.sqrt
_sin = math.sin
_cos = math.cos
_PI = math.pi

c1 = 1.70158
c2 = c1 * 1.525
c3 = c1 + 1
c4 = (2 * _PI) / 3
c5 = (2 * _PI) / 4.5


def _bounce_out(x: float) -> float:
    """保持 TypeScript 原版 bounceOut 的结构，不优化重构。

    注意：TS 原版使用 ``x -= offset`` 原地修改后再平方，
    因此每个分支必须先更新 x 再计算 n1 * x * x。
    """
    n1 = 7.5625
    d1 = 2.75

    if x < 1 / d1:
        return n1 * x * x
    elif x < 2 / d1:
        x -= 1.5 / d1
        return n1 * x * x + 0.75
    elif x < 2.5 / d1:
        x -= 2.25 / d1
        return n1 * x * x + 0.9375
    else:
        x -= 2.625 / d1
        return n1 * x * x + 0.984375


# 缓动类型编号 → 函数名 映射表
EASING_TYPE_TO_NAME: dict[int, str] = {
    1: "linear",
    2: "easeOutSine",
    3: "easeInSine",
    4: "easeOutQuad",
    5: "easeInQuad",
    6: "easeInOutSine",
    7: "easeInOutQuad",
    8: "easeOutCubic",
    9: "easeInCubic",
    10: "easeOutQuart",
    11: "easeInQuart",
    12: "easeInOutCubic",
    13: "easeInOutQuart",
    14: "easeOutQuint",
    15: "easeInQuint",
    16: "easeOutExpo",
    17: "easeInExpo",
    18: "easeOutCirc",
    19: "easeInCirc",
    20: "easeOutBack",
    21: "easeInBack",
    22: "easeInOutCirc",
    23: "easeInOutBack",
    24: "easeOutElastic",
    25: "easeInElastic",
    26: "easeOutBounce",
    27: "easeInBounce",
    28: "easeInOutBounce",
    29: "easeInOutElastic",
}


def linear(x: float) -> float:
    return x


def ease_in_quad(x: float) -> float:
    return x * x


def ease_out_quad(x: float) -> float:
    return 1 - (1 - x) * (1 - x)


def ease_in_out_quad(x: float) -> float:
    return 2 * x * x if x < 0.5 else 1 - _pow(-2 * x + 2, 2) / 2


def ease_in_cubic(x: float) -> float:
    return x * x * x


def ease_out_cubic(x: float) -> float:
    return 1 - _pow(1 - x, 3)


def ease_in_out_cubic(x: float) -> float:
    return 4 * x * x * x if x < 0.5 else 1 - _pow(-2 * x + 2, 3) / 2


def ease_in_quart(x: float) -> float:
    return x * x * x * x


def ease_out_quart(x: float) -> float:
    return 1 - _pow(1 - x, 4)


def ease_in_out_quart(x: float) -> float:
    return 8 * x * x * x * x if x < 0.5 else 1 - _pow(-2 * x + 2, 4) / 2


def ease_in_quint(x: float) -> float:
    return x * x * x * x * x


def ease_out_quint(x: float) -> float:
    return 1 - _pow(1 - x, 5)


def ease_in_out_quint(x: float) -> float:
    return 16 * x * x * x * x * x if x < 0.5 else 1 - _pow(-2 * x + 2, 5) / 2


def ease_in_sine(x: float) -> float:
    return 1 - _cos((x * _PI) / 2)


def ease_out_sine(x: float) -> float:
    return _sin((x * _PI) / 2)


def ease_in_out_sine(x: float) -> float:
    return -(_cos(_PI * x) - 1) / 2


def ease_in_expo(x: float) -> float:
    return 0 if x == 0 else _pow(2, 10 * x - 10)


def ease_out_expo(x: float) -> float:
    return 1 if x == 1 else 1 - _pow(2, -10 * x)


def ease_in_out_expo(x: float) -> float:
    if x == 0:
        return 0
    if x == 1:
        return 1
    return _pow(2, 20 * x - 10) / 2 if x < 0.5 else (2 - _pow(2, -20 * x + 10)) / 2


def ease_in_circ(x: float) -> float:
    return 1 - _sqrt(1 - _pow(x, 2))


def ease_out_circ(x: float) -> float:
    return _sqrt(1 - _pow(x - 1, 2))


def ease_in_out_circ(x: float) -> float:
    if x < 0.5:
        return (1 - _sqrt(1 - _pow(2 * x, 2))) / 2
    return (_sqrt(1 - _pow(-2 * x + 2, 2)) + 1) / 2


def ease_in_back(x: float) -> float:
    return c3 * x * x * x - c1 * x * x


def ease_out_back(x: float) -> float:
    return 1 + c3 * _pow(x - 1, 3) + c1 * _pow(x - 1, 2)


def ease_in_out_back(x: float) -> float:
    if x < 0.5:
        return (_pow(2 * x, 2) * ((c2 + 1) * 2 * x - c2)) / 2
    return (_pow(2 * x - 2, 2) * ((c2 + 1) * (x * 2 - 2) + c2) + 2) / 2


def ease_in_elastic(x: float) -> float:
    if x == 0:
        return 0
    if x == 1:
        return 1
    return -_pow(2, 10 * x - 10) * _sin((x * 10 - 10.75) * c4)


def ease_out_elastic(x: float) -> float:
    if x == 0:
        return 0
    if x == 1:
        return 1
    return _pow(2, -10 * x) * _sin((x * 10 - 0.75) * c4) + 1


def ease_in_out_elastic(x: float) -> float:
    if x == 0:
        return 0
    if x == 1:
        return 1
    if x < 0.5:
        return -(_pow(2, 20 * x - 10) * _sin((20 * x - 11.125) * c5)) / 2
    return (_pow(2, -20 * x + 10) * _sin((20 * x - 11.125) * c5)) / 2 + 1


def ease_in_bounce(x: float) -> float:
    return 1 - _bounce_out(1 - x)


def ease_out_bounce(x: float) -> float:
    return _bounce_out(x)


def ease_in_out_bounce(x: float) -> float:
    if x < 0.5:
        return (1 - _bounce_out(1 - 2 * x)) / 2
    return (1 + _bounce_out(2 * x - 1)) / 2


# 缓动函数字典
EASING_FUNCTIONS: dict[str, EasingFunction] = {
    "linear": linear,
    "easeInQuad": ease_in_quad,
    "easeOutQuad": ease_out_quad,
    "easeInOutQuad": ease_in_out_quad,
    "easeInCubic": ease_in_cubic,
    "easeOutCubic": ease_out_cubic,
    "easeInOutCubic": ease_in_out_cubic,
    "easeInQuart": ease_in_quart,
    "easeOutQuart": ease_out_quart,
    "easeInOutQuart": ease_in_out_quart,
    "easeInQuint": ease_in_quint,
    "easeOutQuint": ease_out_quint,
    "easeInOutQuint": ease_in_out_quint,
    "easeInSine": ease_in_sine,
    "easeOutSine": ease_out_sine,
    "easeInOutSine": ease_in_out_sine,
    "easeInExpo": ease_in_expo,
    "easeOutExpo": ease_out_expo,
    "easeInOutExpo": ease_in_out_expo,
    "easeInCirc": ease_in_circ,
    "easeOutCirc": ease_out_circ,
    "easeInOutCirc": ease_in_out_circ,
    "easeInBack": ease_in_back,
    "easeOutBack": ease_out_back,
    "easeInOutBack": ease_in_out_back,
    "easeInElastic": ease_in_elastic,
    "easeOutElastic": ease_out_elastic,
    "easeInOutElastic": ease_in_out_elastic,
    "easeInBounce": ease_in_bounce,
    "easeOutBounce": ease_out_bounce,
    "easeInOutBounce": ease_in_out_bounce,
}


def get_easing_by_type(easing_type: int) -> EasingFunction:
    """通过缓动类型编号（1-29）获取缓动函数。

    Raises:
        KeyError: 未知缓动类型编号
    """
    return get_easing_by_name(EASING_TYPE_TO_NAME[easing_type])


def get_easing_by_name(name: str) -> EasingFunction:
    """通过名称获取缓动函数。

    Raises:
        KeyError: 未知缓动名称
    """
    return EASING_FUNCTIONS[name]
