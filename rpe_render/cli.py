"""命令行接口：解析参数、构建 RenderConfig 并调用 renderer.render()。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .constants import NOTES_DIR, OUTPUT_DPI, PREVIEW_BG_ALPHA
from .renderer import RenderConfig, render


def parse_args(argv: list[str] | None = None) -> RenderConfig:
    """解析命令行参数并构建 RenderConfig。

    Usage:
        python -m rpe_render chart.json
        python -m rpe_render chart.json --background art.png
        python -m rpe_render chart.json -o output.png
        python -m rpe_render chart.json --bg art.png -o out.png --dpi 300
    """
    parser = argparse.ArgumentParser(
        prog="rpe-render",
        description="RPE 谱面配置预览图生成器",
    )
    parser.add_argument(
        "chart",
        type=Path,
        help="RPE JSON 谱面文件路径",
    )
    parser.add_argument(
        "--background",
        "--bg",
        type=Path,
        default=None,
        help="背景曲绘图片路径（不指定则透明背景）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output.png"),
        help=f"输出 PNG 文件路径（默认: output.png）",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=OUTPUT_DPI,
        help=f"输出 DPI（默认: {OUTPUT_DPI}）",
    )
    parser.add_argument(
        "--notes-dir",
        type=Path,
        default=Path(NOTES_DIR),
        help=f"Note 贴图目录路径（默认: {NOTES_DIR}）",
    )
    parser.add_argument(
        "--preview-bg-alpha",
        type=float,
        default=PREVIEW_BG_ALPHA,
        help=(
            "谱面预览区半透明黑色底色透明度 0.0~1.0"
            f"（默认: {PREVIEW_BG_ALPHA}，0.0 关闭）"
        ),
    )
    args = parser.parse_args(argv)

    return RenderConfig(
        chart_path=args.chart,
        background_path=args.background,
        output_path=args.output,
        notes_dir=args.notes_dir,
        dpi=args.dpi,
        preview_bg_alpha=args.preview_bg_alpha,
    )


def _configure_logging() -> None:
    """CLI 模式默认 WARNING 级别，可通过环境变量 RPE_RENDER_LOG_LEVEL 覆盖。"""
    level_name = os.environ.get("RPE_RENDER_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口函数。"""
    _configure_logging()
    config = parse_args(argv)
    try:
        render(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
