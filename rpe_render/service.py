"""Reusable rendering service used by the CLI and HTTP adapters."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .constants import (
    BACKGROUND_BLUR_SIGMA,
    BACKGROUND_BRIGHTNESS,
    FIT_OFFICIAL_DIVISIONS,
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
    fit_official_divisions: bool = FIT_OFFICIAL_DIVISIONS,
) -> bytes:
    """Render a JSON/PEZ/ZIP source and return PNG or JPEG bytes."""
    normalized_format = output_format.lower().lstrip(".")
    if normalized_format == "jpeg":
        normalized_format = "jpg"
    if normalized_format not in {"png", "jpg"}:
        raise ValueError("output_format must be 'png' or 'jpg'")
    with load_chart_input(source) as chart_input:
        background = Path(background_path) if background_path else chart_input.background_path
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
                    metadata=metadata,
                    background_blur_sigma=background_blur_sigma,
                    background_brightness=background_brightness,
                    fit_official_divisions=fit_official_divisions,
                )
            )
            return output.read_bytes()


__all__ = ["ChartPackageError", "render_source"]
