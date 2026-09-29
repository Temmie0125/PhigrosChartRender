"""Web API 文件上传扩展测试：自定义曲绘与信息文件解析。"""

import io
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from rpe_render.api import app, manager


@pytest.fixture()
def fresh_executor():
    """manager.executor 是模块级单例；前序用例的 lifespan 清理会关闭它，
    提交任务的用例需先恢复一个可用线程池。"""
    original = manager.executor
    manager.executor = ThreadPoolExecutor(max_workers=1)
    yield
    manager.executor.shutdown(wait=False, cancel_futures=True)
    manager.executor = original


def make_png_bytes(color=(255, 0, 0)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buffer, format="PNG")
    return buffer.getvalue()


def wait_for_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get(f"/api/v1/jobs/{job_id}").json()
        if status["status"] in ("succeeded", "failed"):
            return status
        time.sleep(0.2)
    raise AssertionError("render job did not finish in time")


INFO_TEXT = (
    "Chart: chart.json\n"
    "Picture: bg.png\n"
    "Name: 我的世界\n"
    "Level: AT 15\n"
    "Composer: Composer X\n"
    "Charter: Charter Y\n"
)


class TestInfoFileEndpoint:
    def test_parses_info_txt_fields(self):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/charts/info",
                files={"file": ("info.txt", io.BytesIO(INFO_TEXT.encode("utf-8")), "text/plain")},
            )
            assert response.status_code == 200
            assert response.json() == {
                "name": "我的世界",
                "charter": "Charter Y",
                "level": "AT 15",
                "composer": "Composer X",
            }

    def test_missing_fields_default_to_empty(self):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/charts/info",
                files={"file": ("info.txt", io.BytesIO(b"Name: Only Name\n"), "text/plain")},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Only Name"
            assert data["charter"] == ""
            assert data["level"] == ""
            assert data["composer"] == ""

    def test_rejects_non_txt(self):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/charts/info",
                files={"file": ("chart.json", io.BytesIO(b"{}"), "application/json")},
            )
            assert response.status_code == 415


class TestBackgroundUpload:
    def _chart_file(self, path: str = "chart.json") -> dict:
        with open(path, "rb") as fp:
            data = fp.read()
        return {"file": ("chart.json", io.BytesIO(data), "application/json")}

    def test_job_with_background_succeeds_and_affects_output(self, project_root, fresh_executor):
        chart_path = project_root / "tests" / "fixtures" / "minimal_chart.json"
        with TestClient(app) as client:
            base = client.post(
                "/api/v1/jobs",
                files=self._chart_file(str(chart_path)),
                data={"dpi": "72"},
            )
            assert base.status_code == 202
            plain = wait_for_job(client, base.json()["id"])
            assert plain["status"] == "succeeded"

            with_bg = client.post(
                "/api/v1/jobs",
                files={
                    **self._chart_file(str(chart_path)),
                    "background": ("bg.png", io.BytesIO(make_png_bytes()), "image/png"),
                },
                data={"dpi": "72"},
            )
            assert with_bg.status_code == 202
            customized = wait_for_job(client, with_bg.json()["id"])
            assert customized["status"] == "succeeded", customized["error"]

            plain_bytes = client.get(f"/api/v1/jobs/{plain['id']}/result").content
            bg_bytes = client.get(f"/api/v1/jobs/{customized['id']}/result").content
            # 自定义曲绘必须实际参与合成：输出与无曲绘渲染不同。
            assert bg_bytes != plain_bytes

    def test_job_rejects_non_image_background(self, project_root, fresh_executor):
        chart_path = project_root / "tests" / "fixtures" / "minimal_chart.json"
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/jobs",
                files={
                    **self._chart_file(str(chart_path)),
                    "background": ("bg.txt", io.BytesIO(b"not an image"), "text/plain"),
                },
            )
            assert response.status_code == 415
