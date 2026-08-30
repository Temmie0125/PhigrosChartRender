from pathlib import Path
import zipfile

import pytest

from rpe_render.package_loader import (
    MissingPictureError,
    _build_input,
    _select_info_file,
    load_chart_input,
)


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


def test_picture_falls_back_from_json_meta_to_info(tmp_path: Path):
    chart = tmp_path / "chart.json"
    chart.write_text(
        '{"META": {"background": "missing.png"}}',
        encoding="utf-8",
    )
    picture = tmp_path / "info-picture.jpg"
    picture.write_bytes(b"image")
    (tmp_path / "info.txt").write_text(
        "Picture: info-picture.jpg\n",
        encoding="utf-8",
    )

    result = _build_input(tmp_path, strict_picture=True)

    assert result.background_path == picture


def test_picture_falls_back_from_declarations_to_unique_image(tmp_path: Path):
    chart = tmp_path / "chart.json"
    chart.write_text(
        '{"META": {"background": "missing.png"}}',
        encoding="utf-8",
    )
    (tmp_path / "info.txt").write_text(
        "Picture: also-missing.jpg\n",
        encoding="utf-8",
    )
    picture = tmp_path / "only-image.png"
    picture.write_bytes(b"image")

    result = _build_input(tmp_path, strict_picture=True)

    assert result.background_path == picture


def test_picture_raises_when_fallback_is_ambiguous(tmp_path: Path):
    chart = tmp_path / "chart.json"
    chart.write_text(
        '{"META": {"background": "missing.png"}}',
        encoding="utf-8",
    )
    (tmp_path / "first.png").write_bytes(b"image")
    (tmp_path / "second.jpg").write_bytes(b"image")

    with pytest.raises(MissingPictureError, match="未找到曲绘"):
        _build_input(tmp_path, strict_picture=True)


def test_json_meta_picture_still_has_priority(tmp_path: Path):
    chart = tmp_path / "chart.json"
    chart.write_text(
        '{"META": {"background": "meta.png"}}',
        encoding="utf-8",
    )
    meta_picture = tmp_path / "meta.png"
    meta_picture.write_bytes(b"image")
    info_picture = tmp_path / "info.jpg"
    info_picture.write_bytes(b"image")
    (tmp_path / "info.txt").write_text(
        "Picture: info.jpg\n",
        encoding="utf-8",
    )

    result = _build_input(tmp_path, strict_picture=True)

    assert result.background_path == meta_picture


def test_zip_upload_uses_picture_fallback_chain(tmp_path: Path):
    package = tmp_path / "chart.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(
            "chart.json",
            '{"META": {"background": "missing.png"}}',
        )
        archive.writestr("info.txt", "Picture: fallback.jpg\n")
        archive.writestr("fallback.jpg", b"image")

    with load_chart_input(package) as result:
        assert result.background_path is not None
        assert result.background_path.name == "fallback.jpg"
        assert result.background_path.is_file()
