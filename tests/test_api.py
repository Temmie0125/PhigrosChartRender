"""Web API 渲染参数测试。"""

import asyncio
import time

import pytest
from pydantic import ValidationError

import rpe_render.api as api_module
from rpe_render.api import Job, RenderOptions, _format_render_error, app, lifespan, manager


def test_column_beats_defaults_to_auto():
    options = RenderOptions()
    assert options.smart_column_beats is True
    assert options.column_beats == 64
    assert options.tile_workers == 0


@pytest.mark.parametrize("value", [12, 18, 132])
def test_column_beats_rejects_invalid_value(value):
    with pytest.raises(ValidationError):
        RenderOptions(smart_column_beats=False, column_beats=value)


@pytest.mark.parametrize("value", [-1, 33])
def test_tile_workers_rejects_invalid_value(value):
    with pytest.raises(ValidationError):
        RenderOptions(tile_workers=value)


def test_render_error_keeps_exception_details():
    assert _format_render_error(ValueError("bad canvas size")) == (
        "ValueError: bad canvas size"
    )


def test_job_manager_exposes_unexpected_render_error(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text("{}")
    job = Job(
        id="test-job",
        source_path=source,
        work_dir=tmp_path,
        options=RenderOptions(),
        created_at=time.time(),
    )

    def fail_render(*_args, **_kwargs):
        raise RuntimeError("tile worker failed")

    monkeypatch.setattr(api_module, "render_source", fail_render)
    manager._run(job)

    assert job.status == "failed"
    assert job.error == "RuntimeError: tile worker failed"
    assert not source.exists()


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
