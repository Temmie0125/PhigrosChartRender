from pathlib import Path

from rpe_render.package_loader import _build_input, _select_info_file


def test_info_file_fallback_chain(tmp_path: Path):
    chart = tmp_path / "chart.json"
    chart.write_text("{}", encoding="utf-8")

    same_name = tmp_path / "chart.txt"
    same_name.write_text("Name: Same\n", encoding="utf-8")
    assert _select_info_file(tmp_path, [chart]) == same_name

    same_name.unlink()
    unique = tmp_path / "metadata.txt"
    unique.write_text("Name: Unique\n", encoding="utf-8")
    assert _select_info_file(tmp_path, [chart]) == unique

    (tmp_path / "other.txt").write_text("Name: Other\n", encoding="utf-8")
    assert _select_info_file(tmp_path, [chart]) is None


def test_archive_name_txt_is_considered_same_name(tmp_path: Path):
    chart = tmp_path / "IN.json"
    chart.write_text("{}", encoding="utf-8")
    archive_info = tmp_path / "Burn.txt"
    archive_info.write_text("Name: Burn\n", encoding="utf-8")
    assert _select_info_file(tmp_path, [chart], "Burn") == archive_info


def test_info_txt_has_priority_and_populates_metadata(tmp_path: Path):
    chart = tmp_path / "chart.json"
    chart.write_text("{}", encoding="utf-8")
    (tmp_path / "chart.txt").write_text("Name: Same\n", encoding="utf-8")
    info = tmp_path / "info.txt"
    info.write_text(
        "Name: Preferred\nLevel: IN Lv.15\nComposer: Composer\nCharter: Charter\n",
        encoding="utf-8",
    )
    result = _build_input(tmp_path, strict_picture=False)
    assert result.metadata == {
        "name": "Preferred",
        "level": "IN Lv.15",
        "composer": "Composer",
        "charter": "Charter",
    }
