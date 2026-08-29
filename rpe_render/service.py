"""Reusable rendering service used by the CLI and HTTP adapters."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .constants import (
    BACKGROUND_BLUR_SIGMA,
    BACKGROUND_BRIGHTNESS,
    FIT_OFFICIAL_DIVISIONS,
    SMART_COLUMN_BEATS,
    COLUMN_BEATS,
)
from .package_loader import ChartPackageError, load_chart_input
from .renderer import RenderConfig, render


def render_source(
    source: str | Path,
    *,
    background_path: str | Path | None = None,
    notes_dir: str | Path = "resources/notes",
    dpi: int = 150,
    preview_bg_alpha: float = 0.55,
    track_bg_alpha: float = 0.75,
    output_format: str = "png",
    metadata: dict[str, str] | None = None,
    background_blur_sigma: float = BACKGROUND_BLUR_SIGMA,
    background_brightness: float = BACKGROUND_BRIGHTNESS,
    tile_workers: int | None = None,
    fit_official_divisions: bool = FIT_OFFICIAL_DIVISIONS,
    smart_column_beats: bool = SMART_COLUMN_BEATS,
    column_beats: int = COLUMN_BEATS,
) -> bytes:
    """Render a JSON/PEZ/ZIP source and return PNG or JPEG bytes."""
    normalized_format = output_format.lower().lstrip(".")
    if normalized_format == "jpeg":
        normalized_format = "jpg"
    if normalized_format not in {"png", "jpg"}:
        raise ValueError("output_format must be 'png' or 'jpg'")
    with load_chart_input(source) as chart_input:
        background = Path(background_path) if background_path else chart_input.background_path
        # 谱面包（尤其官谱）可能没有 META；info.txt 元数据作为默认值，
        # 调用方显式传入的 metadata 覆盖包内值。
        effective_metadata = dict(chart_input.metadata)
        effective_metadata.update(metadata or {})
        with tempfile.TemporaryDirectory(prefix="rpe-render-") as output_dir:
            output = Path(output_dir) / f"preview.{normalized_format}"
            render(
                RenderConfig(
                    chart_path=chart_input.chart_path,
                    background_path=background,
                    output_path=output,
                    output_format=normalized_format,
                    notes_dir=notes_dir,
                    dpi=dpi,
                    preview_bg_alpha=preview_bg_alpha,
                    track_bg_alpha=track_bg_alpha,
                    metadata=effective_metadata,
                    background_blur_sigma=background_blur_sigma,
                    background_brightness=background_brightness,
                    tile_workers=tile_workers,
                    fit_official_divisions=fit_official_divisions,
                    smart_column_beats=smart_column_beats,
                    column_beats=column_beats,
                )
            )
            return output.read_bytes()


__all__ = ["ChartPackageError", "render_source"]
