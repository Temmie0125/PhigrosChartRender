"""FastAPI application for asynchronous chart rendering."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .chart_parser import parse_chart
from .constants import (
    BACKGROUND_BLUR_SIGMA,
    BACKGROUND_BRIGHTNESS,
    FIT_OFFICIAL_DIVISIONS,
)
from .package_loader import ChartPackageError, load_chart_input
from .service import render_source


class RenderOptions(BaseModel):
    dpi: int = Field(150, ge=72, le=600)
    format: Literal["png", "jpg"] = "png"
    preview_bg_alpha: float = Field(0.55, ge=0.0, le=1.0)
    track_bg_alpha: float = Field(0.75, ge=0.0, le=1.0)
    name: str | None = Field(None, max_length=200)
    charter: str | None = Field(None, max_length=200)
    level: str | None = Field(None, max_length=80)
    composer: str | None = Field(None, max_length=200)
    background_blur_sigma: float = Field(BACKGROUND_BLUR_SIGMA, ge=0.0, le=100.0)
    background_brightness: float = Field(BACKGROUND_BRIGHTNESS, ge=0.0, le=2.0)
    fit_official_divisions: bool = FIT_OFFICIAL_DIVISIONS


class ChartMetadataResponse(BaseModel):
    name: str
    charter: str
    level: str
    composer: str


class JobResponse(BaseModel):
    id: str
    status: str
    progress: int
    error: str | None = None
    result_url: str | None = None


@dataclass
class Job:
    id: str
    source_path: Path
    work_dir: Path
    options: RenderOptions
    created_at: float
    status: str = "queued"
    progress: int = 0
    error: str | None = None
    result_path: Path | None = None


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.environ.get(name, default)))
    except ValueError:
        return default


class JobManager:
    def __init__(self) -> None:
        self.root = Path(os.environ.get("RPE_API_RUNTIME_DIR", tempfile.gettempdir())) / "rpe-render-api"
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self.executor = ThreadPoolExecutor(
            max_workers=_env_int("RPE_RENDER_WORKERS", 1, 1)
        )
        self.max_jobs = _env_int("RPE_MAX_QUEUE_SIZE", 32, 1)
        self.result_ttl = _env_int("RPE_RESULT_TTL_SECONDS", 1800, 60)
        self.max_upload = _env_int("RPE_MAX_UPLOAD_BYTES", 256 * 1024 * 1024, 1)
        self.rate_limit = _env_int("RPE_RATE_LIMIT_PER_MINUTE", 60, 0)
        self.request_times: dict[str, list[float]] = {}

    def cleanup(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)
        shutil.rmtree(self.root, ignore_errors=True)

    def purge_expired(self) -> None:
        now = time.time()
        for job_id, job in list(self.jobs.items()):
            if now - job.created_at > self.result_ttl:
                shutil.rmtree(job.work_dir, ignore_errors=True)
                self.jobs.pop(job_id, None)

    async def create(self, upload: UploadFile, options: RenderOptions) -> Job:
        self.purge_expired()
        active = sum(job.status in {"queued", "running"} for job in self.jobs.values())
        if active >= self.max_jobs:
            raise HTTPException(status_code=429, detail="渲染任务队列已满")
        suffix = Path(upload.filename or "chart.zip").suffix.lower()
        if suffix not in {".json", ".pez", ".zip"}:
            raise HTTPException(status_code=415, detail="仅支持 JSON、PEZ 或 ZIP 文件")
        job_id = uuid.uuid4().hex
        work_dir = self.root / job_id
        work_dir.mkdir(parents=True, exist_ok=False)
        source = work_dir / f"source{suffix}"
        size = 0
        try:
            with source.open("wb") as dst:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.max_upload:
                        raise HTTPException(status_code=413, detail="上传文件超过大小限制")
                    dst.write(chunk)
        except Exception:
            shutil.rmtree(work_dir, ignore_errors=True)
            raise
        job = Job(job_id, source, work_dir, options, time.time())
        self.jobs[job_id] = job
        self.executor.submit(self._run, job)
        return job

    def check_rate(self, client: str) -> None:
        if self.rate_limit <= 0 or os.environ.get("RPE_LOCAL_MODE", "false").lower() == "true":
            return
        now = time.time()
        recent = [t for t in self.request_times.get(client, []) if now - t < 60]
        if len(recent) >= self.rate_limit:
            raise HTTPException(status_code=429, detail="请求频率超过限制")
        recent.append(now)
        self.request_times[client] = recent

    def _run(self, job: Job) -> None:
        job.status, job.progress = "running", 5
        try:
            data = render_source(
                job.source_path,
                dpi=job.options.dpi,
                output_format=job.options.format,
                preview_bg_alpha=job.options.preview_bg_alpha,
                track_bg_alpha=job.options.track_bg_alpha,
                metadata={
                    key: value
                    for key, value in {
                        "name": job.options.name,
                        "charter": job.options.charter,
                        "level": job.options.level,
                        "composer": job.options.composer,
                    }.items()
                    if value is not None
                },
                background_blur_sigma=job.options.background_blur_sigma,
                background_brightness=job.options.background_brightness,
                fit_official_divisions=job.options.fit_official_divisions,
            )
            result = job.work_dir / f"preview.{job.options.format}"
            result.write_bytes(data)
            job.result_path = result
            job.status, job.progress = "succeeded", 100
        except (ChartPackageError, FileNotFoundError, ValueError) as exc:
            job.status, job.error = "failed", str(exc)
        except Exception:
            job.status, job.error = "failed", "渲染失败"
        finally:
            try:
                job.source_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get(self, job_id: str) -> Job:
        self.purge_expired()
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="任务不存在或已过期")
        return job


manager = JobManager()
app = FastAPI(title="Phigros Preview Renderer API", version="1.0.0")
_cors_origins = [
    origin.strip()
    for origin in os.environ.get(
        "RPE_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    # 结果只存在本地临时目录；重启后所有旧任务均视为无效。
    manager.root.mkdir(parents=True, exist_ok=True)
    for child in manager.root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


@app.on_event("shutdown")
async def shutdown() -> None:
    manager.cleanup()


def _response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        status=job.status,
        progress=job.progress,
        error=job.error,
        result_url=f"/api/v1/jobs/{job.id}/result" if job.status == "succeeded" else None,
    )


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/jobs", response_model=JobResponse, status_code=202)
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    dpi: int = Form(150),
    format: Literal["png", "jpg"] = Form("png"),
    preview_bg_alpha: float = Form(0.55),
    track_bg_alpha: float = Form(0.75),
    name: str | None = Form(None),
    charter: str | None = Form(None),
    level: str | None = Form(None),
    composer: str | None = Form(None),
    background_blur_sigma: float = Form(BACKGROUND_BLUR_SIGMA),
    background_brightness: float = Form(BACKGROUND_BRIGHTNESS),
    fit_official_divisions: bool = Form(FIT_OFFICIAL_DIVISIONS),
) -> JobResponse:
    manager.check_rate(request.client.host if request.client else "unknown")
    options = RenderOptions(
        dpi=dpi,
        format=format,
        preview_bg_alpha=preview_bg_alpha,
        track_bg_alpha=track_bg_alpha,
        name=name,
        charter=charter,
        level=level,
        composer=composer,
        background_blur_sigma=background_blur_sigma,
        background_brightness=background_brightness,
        fit_official_divisions=fit_official_divisions,
    )
    return _response(await manager.create(file, options))


@app.post("/api/v1/charts/metadata", response_model=ChartMetadataResponse)
async def read_chart_metadata(file: UploadFile = File(...)) -> ChartMetadataResponse:
    """读取上传谱面的四项可编辑元数据，不创建渲染任务。"""
    suffix = Path(file.filename or "chart.zip").suffix.lower()
    if suffix not in {".json", ".pez", ".zip"}:
        raise HTTPException(status_code=415, detail="仅支持 JSON、PEZ 或 ZIP 文件")
    temp_root = Path(tempfile.mkdtemp(prefix="rpe-metadata-"))
    source = temp_root / f"source{suffix}"
    size = 0
    try:
        with source.open("wb") as dst:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > manager.max_upload:
                    raise HTTPException(status_code=413, detail="上传文件超过大小限制")
                dst.write(chunk)
        with load_chart_input(source, strict_picture=False) as chart_input:
            meta = parse_chart(chart_input.chart_path).meta
            # 官谱包通常没有 META；谱面包加载器已从 info.txt 提取默认值。
            # JSON META（若存在）优先于 info.txt，空字段再回退到包内信息。
            package_metadata = chart_input.metadata
            name = meta.name or package_metadata.get("name", "")
            charter = meta.charter or package_metadata.get("charter", "")
            level = meta.level or package_metadata.get("level", "")
            composer = meta.composer or package_metadata.get("composer", "")
        return ChartMetadataResponse(
            name=name,
            charter=charter,
            level=level,
            composer=composer,
        )
    except HTTPException:
        raise
    except (ChartPackageError, FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    return _response(manager.get(job_id))


@app.get("/api/v1/jobs/{job_id}/result")
async def get_result(job_id: str) -> Any:
    job = manager.get(job_id)
    if job.status != "succeeded" or job.result_path is None:
        raise HTTPException(status_code=409, detail="任务尚未完成")
    media_type = "image/jpeg" if job.options.format == "jpg" else "image/png"
    return FileResponse(
        job.result_path,
        media_type=media_type,
        filename=f"preview.{job.options.format}",
    )


@app.delete("/api/v1/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str) -> None:
    job = manager.get(job_id)
    shutil.rmtree(job.work_dir, ignore_errors=True)
    manager.jobs.pop(job_id, None)


__all__ = ["app"]
