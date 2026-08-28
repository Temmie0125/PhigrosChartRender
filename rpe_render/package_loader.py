"""Load RPE JSON files and PEZ/ZIP chart packages safely."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


class ChartPackageError(ValueError):
    """Base error for malformed chart packages."""


class PackageFormatError(ChartPackageError):
    """The package layout or chart declaration is invalid."""


class MissingPictureError(ChartPackageError):
    """A declared illustration cannot be found or is unsupported."""


_INFO_KEYS = {
    "Chart",
    "Picture",
    "Name",
    "Path",
    "Song",
    "Level",
    "Composer",
    "Illustrator",
    "Charter",
}
_DIRECTIVE_RE = re.compile(
    r"^\s*(Chart|Picture|Name|Path|Song|Level|Composer|Illustrator|Charter)"
    r"\s*:\s*(.*?)\s*$"
)
_FORBIDDEN_CHARS = set('<>:"/\\|?*')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_FILES = 4096
_MAX_UPLOAD_BYTES = 256 * 1024 * 1024


@dataclass
class ChartInput:
    chart_path: Path
    background_path: Path | None
    metadata: dict[str, str] = field(default_factory=dict)
    _temporary_root: Path | None = None

    def cleanup(self) -> None:
        if self._temporary_root is not None:
            shutil.rmtree(self._temporary_root, ignore_errors=True)
            self._temporary_root = None

    def __enter__(self) -> "ChartInput":
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()


def _validate_component(name: str) -> None:
    if not name or name in {".", ".."}:
        raise PackageFormatError("谱面包格式错误：存在非法路径")
    if any(ord(ch) < 32 or ch in _FORBIDDEN_CHARS for ch in name):
        raise PackageFormatError(f"谱面包格式错误：文件名包含系统保留字符：{name}")
    if name.endswith((".", " ")):
        raise PackageFormatError(f"谱面包格式错误：文件名不能以空格或点结尾：{name}")
    if name.split(".", 1)[0].upper() in _RESERVED_NAMES:
        raise PackageFormatError(f"谱面包格式错误：文件名为系统保留名称：{name}")


def _safe_relative(value: str, *, root_only: bool = False) -> Path:
    value = value.strip()
    if not value or Path(value).is_absolute() or "\\" in value:
        raise PackageFormatError("谱面包格式错误：声明路径必须是相对路径")
    path = Path(value)
    if root_only and len(path.parts) != 1:
        raise PackageFormatError("谱面包格式错误：Chart 必须位于谱面包根目录")
    for part in path.parts:
        _validate_component(part)
    return path


def _read_info(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise PackageFormatError("谱面包格式错误：无法读取 info.txt") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = _DIRECTIVE_RE.match(line)
        if match:
            key, value = match.groups()
            if value:
                values[key] = value
    return values


def _read_meta_background(chart_path: Path) -> str | None:
    try:
        raw = json.loads(chart_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackageFormatError("谱面包格式错误：谱面 JSON 无法解析") from exc
    meta = raw.get("META") if isinstance(raw, dict) else None
    if not isinstance(meta, dict):
        return None
    value = meta.get("background")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _is_official_chart(chart_path: Path) -> bool:
    """轻量识别官谱结构，供谱面包资源解析使用。"""
    try:
        raw = json.loads(chart_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict) or "BPMList" in raw or "META" in raw:
        return False
    if "formatVersion" in raw or "formatversion" in raw:
        return True
    lines = raw.get("judgeLineList")
    return isinstance(lines, list) and any(
        isinstance(line, dict)
        and ("notesAbove" in line or "notesBelow" in line)
        for line in lines
    )


def _resolve_picture(
    root: Path,
    chart_path: Path,
    info: dict[str, str],
    *,
    strict: bool,
    allow_official_unique: bool = False,
) -> Path | None:
    official = _is_official_chart(chart_path)
    # 官谱没有资源声明：若包体内只有一个可用图片资源，优先使用它；
    # 否则再回退到 info.txt 的 Picture 指定。
    if official and allow_official_unique:
        pictures = sorted(
            p for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        )
        if len(pictures) == 1:
            return pictures[0]
    declared = _read_meta_background(chart_path) or info.get("Picture")
    if not declared:
        if strict:
            raise MissingPictureError("未找到曲绘")
        return None
    try:
        relative = _safe_relative(declared)
    except PackageFormatError as exc:
        if strict:
            raise MissingPictureError("未找到曲绘") from exc
        return None
    picture = (root / relative).resolve()
    if root.resolve() not in picture.parents or not picture.is_file():
        if strict:
            raise MissingPictureError("未找到曲绘")
        return None
    if picture.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        if strict:
            raise MissingPictureError("未找到曲绘")
        return None
    return picture


def _select_info_file(
    root: Path,
    json_files: list[Path],
    source_stem: str | None = None,
) -> Path | None:
    """按优先级选择谱面包信息文件。

    官谱包的约定并不统一：优先使用根目录 ``info.txt``，其次查找与
    谱面 JSON 同名的 ``.txt``，最后仅在包内恰好只有一个 txt 时使用它。
    """
    preferred = root / "info.txt"
    if preferred.is_file():
        return preferred

    chart_stems = {path.stem for path in json_files}
    if source_stem:
        chart_stems.add(source_stem)
    txt_files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".txt"
    )
    same_name = [path for path in txt_files if path.stem in chart_stems]
    if len(same_name) == 1:
        return same_name[0]

    return txt_files[0] if len(txt_files) == 1 else None


def _build_input(
    root: Path,
    *,
    strict_picture: bool,
    source_stem: str | None = None,
) -> ChartInput:
    json_files = sorted(p for p in root.iterdir() if p.is_file() and p.suffix == ".json")
    info_path = _select_info_file(root, json_files, source_stem)
    info = _read_info(info_path) if info_path is not None else {}
    chart_name = info.get("Chart") if len(json_files) != 1 else json_files[0].name
    if not chart_name:
        raise PackageFormatError("谱面包格式错误：根目录存在多个 JSON 但缺少 Chart 声明")
    try:
        chart_rel = _safe_relative(chart_name, root_only=True)
    except PackageFormatError as exc:
        raise PackageFormatError("谱面包格式错误：Chart 声明无效") from exc
    chart_path = root / chart_rel
    if not chart_path.is_file() or chart_path.suffix != ".json":
        raise PackageFormatError("谱面包格式错误：未找到声明的谱面 JSON")
    background = _resolve_picture(
        root,
        chart_path,
        info,
        strict=strict_picture,
        allow_official_unique=True,
    )
    # 官谱 JSON 通常不含 META；info.txt 是谱面包的元数据来源。
    metadata = {
        target: info[source]
        for target, source in {
            "name": "Name",
            "level": "Level",
            "composer": "Composer",
            "charter": "Charter",
        }.items()
        if info.get(source)
    }
    return ChartInput(chart_path, background, metadata)


def _extract_zip(source: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if len(members) > _MAX_ARCHIVE_FILES:
                raise PackageFormatError("谱面包格式错误：文件数量超限")
            total = 0
            for member in members:
                name = member.filename.replace("\\", "/")
                if name.endswith("/"):
                    continue
                relative = _safe_relative(name)
                target = (destination / relative).resolve()
                if destination.resolve() not in target.parents:
                    raise PackageFormatError("谱面包格式错误：包含非法路径")
                total += member.file_size
                if total > _MAX_ARCHIVE_BYTES:
                    raise PackageFormatError("谱面包格式错误：解压后大小超限")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
    except zipfile.BadZipFile as exc:
        raise PackageFormatError("谱面包格式错误：不是有效的 ZIP/PEZ 文件") from exc


@contextmanager
def load_chart_input(source: str | Path, *, strict_picture: bool = True) -> Iterator[ChartInput]:
    """Resolve a JSON/PEZ/ZIP source into a temporary, validated chart input."""
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size > _MAX_UPLOAD_BYTES:
        raise ChartPackageError("输入文件超过大小限制")
    if path.suffix.lower() == ".json":
        result = ChartInput(path, None)
        result.background_path = _resolve_picture(path.parent, path, {}, strict=False)
        try:
            yield result
        finally:
            result.cleanup()
        return
    if path.suffix.lower() not in {".pez", ".zip"}:
        raise PackageFormatError("仅支持 JSON、PEZ 或 ZIP 文件")
    temporary_root = Path(tempfile.mkdtemp(prefix="rpe-chart-"))
    try:
        _extract_zip(path, temporary_root)
        result = _build_input(
            temporary_root,
            strict_picture=strict_picture,
            source_stem=path.stem,
        )
        result._temporary_root = temporary_root
        yield result
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


__all__ = [
    "ChartInput",
    "ChartPackageError",
    "MissingPictureError",
    "PackageFormatError",
    "load_chart_input",
]
