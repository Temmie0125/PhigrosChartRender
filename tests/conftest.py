"""pytest 共享 fixtures。"""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESOURCES_DIR = PROJECT_ROOT / "resources"


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def minimal_chart_path() -> Path:
    return FIXTURES_DIR / "minimal_chart.json"


@pytest.fixture(scope="session")
def hold_cross_chart_path() -> Path:
    return FIXTURES_DIR / "hold_cross_column.json"


@pytest.fixture(scope="session")
def multitap_chart_path() -> Path:
    return FIXTURES_DIR / "multitap_chart.json"


@pytest.fixture(scope="session")
def vertical_line_chart_path() -> Path:
    return FIXTURES_DIR / "vertical_line_chart.json"


@pytest.fixture(scope="session")
def real_chart_path() -> Path:
    return RESOURCES_DIR / "chart.json"


@pytest.fixture(scope="session")
def notes_dir() -> Path:
    return RESOURCES_DIR / "notes"
