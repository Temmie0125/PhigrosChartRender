"""Web API 渲染参数测试。"""

import asyncio

import pytest
from pydantic import ValidationError

from rpe_render.api import RenderOptions, app, lifespan, manager


def test_column_beats_defaults_to_auto():
    options = RenderOptions()
    assert options.smart_column_beats is True
    assert options.column_beats == 64


@pytest.mark.parametrize("value", [12, 18, 132])
def test_column_beats_rejects_invalid_value(value):
    with pytest.raises(ValidationError):
        RenderOptions(smart_column_beats=False, column_beats=value)


def test_lifespan_cleans_runtime_directory_and_manager(tmp_path, monkeypatch):
    stale_job = tmp_path / "stale-job"
    stale_job.mkdir()
    cleanup_calls = []
    monkeypatch.setattr(manager, "root", tmp_path)
    monkeypatch.setattr(manager, "cleanup", lambda: cleanup_calls.append(True))

    async def run_lifespan():
        async with lifespan(app):
            assert not stale_job.exists()
            assert cleanup_calls == []

    asyncio.run(run_lifespan())
    assert cleanup_calls == [True]
