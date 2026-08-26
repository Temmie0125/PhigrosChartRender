"""Reusable rendering service used by the CLI and HTTP adapters."""

from __future__ import annotations

import tempfile
from pathlib import Path

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
) -> bytes:
    """Render a JSON/PEZ/ZIP source and return the PNG bytes."""
    with load_chart_input(source) as chart_input:
        background = Path(background_path) if background_path else chart_input.background_path
        with tempfile.TemporaryDirectory(prefix="rpe-render-") as output_dir:
            output = Path(output_dir) / "preview.png"
            render(
                RenderConfig(
                    chart_path=chart_input.chart_path,
                    background_path=background,
                    output_path=output,
                    notes_dir=notes_dir,
                    dpi=dpi,
                    preview_bg_alpha=preview_bg_alpha,
                    track_bg_alpha=track_bg_alpha,
                )
            )
            return output.read_bytes()


__all__ = ["ChartPackageError", "render_source"]
