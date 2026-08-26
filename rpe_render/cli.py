"""命令行接口：解析参数、构建 RenderConfig 并调用 renderer.render()。"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("rpe_render")


def _extract_config_path(argv: list[str]) -> str | None:
    """从原始参数中提取 --config 路径。

    必须在导入任何 rpe_render 模块之前调用：配置需先于其他模块生效，
    这样各模块 import 到的常量默认值才能反映配置文件覆盖。
    """
    it = iter(argv)
    for token in it:
        if token == "--config":
            try:
                return next(it)
            except StopIteration:
                return None
        if token.startswith("--config="):
            return token.split("=", 1)[1]
    return None


def parse_args(argv: list[str] | None = None):
    """解析命令行参数并构建 RenderConfig。

    Usage:
        python -m rpe_render chart.json
        python -m rpe_render chart.json --background art.png
        python -m rpe_render chart.json -o output.png --format png --config render_config.json
    """
    # 延迟导入：确保 parse_args 在 main() 应用配置文件之后才被调用，
    # argparse 默认值取自应用过覆盖的常量。
    from .constants import (
        CONFIG_FILE_NAME,
        NOTES_DIR,
        OUTPUT_DPI,
        PREVIEW_BG_ALPHA,
        TRACK_BG_ALPHA,
    )
    from .renderer import RenderConfig

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
        "--config",
        type=Path,
        default=None,
        help=f"配置文件路径（默认: 当前目录下的 {CONFIG_FILE_NAME}）",
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
        help="输出图片文件路径（默认: output.png）",
    )
    parser.add_argument(
        "--format",
        choices=("png", "jpg", "jpeg"),
        default=None,
        help="输出格式；未指定时按输出文件扩展名推断（png/jpg）",
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
    parser.add_argument(
        "--track-bg-alpha",
        type=float,
        default=TRACK_BG_ALPHA,
        help=(
            "每条 Note 轨道区域额外加深透明度 0.0~1.0"
            f"（默认: {TRACK_BG_ALPHA}，0.0 关闭）"
        ),
    )
    args = parser.parse_args(argv)
    raw_args = list(argv) if argv is not None else sys.argv[1:]
    output_path = args.output
    has_explicit_output = any(
        token == "-o"
        or token == "--output"
        or token.startswith("--output=")
        for token in raw_args
    )
    if args.format and not has_explicit_output:
        suffix = "jpg" if args.format == "jpeg" else args.format
        output_path = Path(f"output.{suffix}")

    return RenderConfig(
        chart_path=args.chart,
        background_path=args.background,
        output_path=output_path,
        output_format=args.format,
        notes_dir=args.notes_dir,
        dpi=args.dpi,
        preview_bg_alpha=args.preview_bg_alpha,
        track_bg_alpha=args.track_bg_alpha,
    )


def _configure_logging() -> None:
    """CLI 模式默认 WARNING 级别，可通过环境变量 RPE_RENDER_LOG_LEVEL 覆盖。"""
    level_name = os.environ.get("RPE_RENDER_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口函数。"""
    _configure_logging()
    argv_list = list(argv) if argv is not None else sys.argv[1:]

    # 先应用配置文件（优先级: --config > 环境变量 > 默认 render_config.json），
    # 再导入渲染模块，保证所有默认值都反映配置覆盖。
    from .constants import CONFIG_ENV_VAR, load_config

    config_path = _extract_config_path(argv_list)
    if config_path:
        os.environ[CONFIG_ENV_VAR] = config_path
        logger.info("Using config file: %s", config_path)
    load_config()

    config = parse_args(argv_list)
    from .renderer import render
    from .service import render_source

    try:
        suffix = Path(config.chart_path).suffix.lower()
        if suffix in {".pez", ".zip"}:
            image = render_source(
                config.chart_path,
                background_path=config.background_path,
                notes_dir=config.notes_dir,
                dpi=config.dpi,
                output_format=config.output_format,
                preview_bg_alpha=config.preview_bg_alpha,
                track_bg_alpha=config.track_bg_alpha,
            )
            Path(config.output_path).write_bytes(image)
        else:
            render(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
