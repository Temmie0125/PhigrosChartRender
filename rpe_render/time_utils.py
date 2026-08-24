"""RPE TimeT 三元组格式与拍数（float）之间的转换工具。

TimeT 格式为 [integer, numerator, denominator]，表示 integer + numerator / denominator。
"""

from __future__ import annotations

# TimeT: RPE 的三元组时间表示 [integer, numerator, denominator]
TimeT = tuple[int, int, int]

# 拍数（浮点数）
Beat = float


def timet_to_beats(tt: tuple[int, int, int]) -> float:
    """将 TimeT [integer, numerator, denominator] 转换为拍数（浮点数）。

    Args:
        tt: TimeT 三元组，表示 integer + numerator / denominator

    Returns:
        对应的拍数值（float）

    Raises:
        ValueError: 若 denominator == 0

    Examples:
        >>> timet_to_beats([0, 0, 1])
        0.0
        >>> timet_to_beats([3, 1, 4])
        3.25
        >>> timet_to_beats([1, 2, 3])
        1.6666666666666667
    """
    if tt[2] == 0:
        raise ValueError("denominator cannot be zero")
    return float(tt[0] + tt[1] / tt[2])


def beats_to_timet(beat: float) -> list[int]:
    """将拍数（浮点数）反向转换为 TimeT 三元组的近似表示。

    用于调试和日志输出，非核心渲染路径。
    denominator 固定为 4（对应十六分音符精度）。
    """
    denom = 4
    total = round(beat * denom)
    integer = total // denom
    numerator = total - integer * denom
    return [integer, numerator, denom]


def timet_compare(a: TimeT, b: TimeT) -> int:
    """比较两个 TimeT 的时间先后。

    返回 -1 (a<b), 0 (a==b), 1 (a>b)。
    不使用浮点转换，完全通过整数运算交叉相乘比较，保证精度。

    Raises:
        ValueError: 若任一 denominator == 0
    """
    if a[2] == 0 or b[2] == 0:
        raise ValueError("denominator cannot be zero")
    # a = a0 + a1/a2, b = b0 + b1/b2
    # a > b  <=>  (a0*a2 + a1) * b2 > (b0*b2 + b1) * a2 （分母均为正时）
    # 为支持负分母，先归一化分母符号
    a_int, a_num, a_den = a
    b_int, b_num, b_den = b
    if a_den < 0:
        a_int, a_num, a_den = -a_int, -a_num, -a_den
    if b_den < 0:
        b_int, b_num, b_den = -b_int, -b_num, -b_den
    left = (a_int * a_den + a_num) * b_den
    right = (b_int * b_den + b_num) * a_den
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def is_same_start_time(a: TimeT, b: TimeT) -> bool:
    """判断两个 TimeT 的三个分量是否完全相同（用于多押判定）。"""
    return a[0] == b[0] and a[1] == b[1] and a[2] == b[2]
