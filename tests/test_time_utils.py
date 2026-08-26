"""time_utils 单元测试。"""

import pytest

from rpe_render.time_utils import (
    beats_to_timet,
    is_same_start_time,
    timet_compare,
    timet_to_beats,
)


class TestTimetToBeats:
    def test_normal(self):
        assert timet_to_beats((0, 0, 1)) == 0.0
        assert timet_to_beats((3, 1, 4)) == 3.25
        assert timet_to_beats((1, 2, 3)) == pytest.approx(1.6666666666666667)
        assert timet_to_beats((10, 0, 1)) == 10.0

    def test_zero_denominator_raises(self):
        with pytest.raises(ValueError, match="denominator cannot be zero"):
            timet_to_beats((0, 1, 0))

    def test_negative_numerator(self):
        assert timet_to_beats((2, -1, 2)) == 1.5

    def test_improper_fraction(self):
        assert timet_to_beats((1, 5, 2)) == 3.5


class TestBeatsToTimet:
    def test_roundtrip(self):
        for beat in (0.0, 1.0, 3.25, 63.75, 128.5):
            tt = beats_to_timet(beat)
            assert len(tt) == 3
            assert tt[2] == 4
            assert timet_to_beats(tuple(tt)) == pytest.approx(beat, abs=1e-9)

    def test_format(self):
        assert beats_to_timet(3.25) == [3, 1, 4]


class TestTimetCompare:
    def test_equal(self):
        assert timet_compare((1, 1, 2), (1, 2, 4)) == 0
        assert timet_compare((0, 0, 1), (0, 0, 1)) == 0

    def test_less_and_greater(self):
        assert timet_compare((0, 0, 1), (1, 0, 1)) == -1
        assert timet_compare((1, 0, 1), (0, 0, 1)) == 1
        assert timet_compare((2, 3, 4), (2, 1, 1)) == -1
        assert timet_compare((2, 1, 1), (2, 3, 4)) == 1

    def test_zero_denominator_raises(self):
        with pytest.raises(ValueError):
            timet_compare((0, 0, 0), (0, 0, 1))


class TestIsSameStartTime:
    def test_exact_components(self):
        assert is_same_start_time((1, 1, 4), (1, 1, 4))
        assert not is_same_start_time((1, 1, 4), (1, 2, 8))  # 数值相等但分量不同
