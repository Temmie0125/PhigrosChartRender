"""Load RPE JSON files and PEZ/ZIP chart packages safely."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class ChartPackageError(ValueError):
    """Base error for malformed chart packages."""


class PackageFormatError(ChartPackageError):
    """The package layout or chart declaration is invalid."""


class MissingPictureError(ChartPackageError):
    """A declared illustration cannot be found or is unsupported."""


_INFO_KEYS = {"Chart", "Picture"}
_DIRECTIVE_RE = re.compile(r"^\s*(Chart|Picture)\s*:\s*(.*?)\s*$")
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


def _resolve_picture(root: Path, chart_path: Path, info: dict[str, str], *, strict: bool) -> Path | None:
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


def _build_input(root: Path, *, strict_picture: bool) -> ChartInput:
    info_path = root / "info.txt"
    info = _read_info(info_path) if info_path.is_file() else {}
    json_files = sorted(p for p in root.iterdir() if p.is_file() and p.suffix == ".json")
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
    background = _resolve_picture(root, chart_path, info, strict=strict_picture)
    return ChartInput(chart_path, background)


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
        result = _build_input(temporary_root, strict_picture=strict_picture)
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
