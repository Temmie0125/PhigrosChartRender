# Web UI 与 API

## 本地启动

在项目根目录安装 Python 依赖后启动 API：

```bash
uvicorn rpe_render.api:app --reload --port 8000
```

启动 React/Vite 前端：

```bash
cd web/frontend
npm install
npm run dev
```

如 API 不在 `http://127.0.0.1:8000`，设置前端环境变量：

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## API

- `GET /api/v1/health`
- `POST /api/v1/charts/metadata`（multipart 字段 `file`；读取 `name`、`charter`、`level`、`composer`，不创建任务）
- `POST /api/v1/jobs`（multipart 字段 `file`，可选 `format`（`png`/`jpg`）、`dpi`、`preview_bg_alpha`、`track_bg_alpha`、`background_blur_sigma`、`background_brightness`、`fit_official_divisions`，以及用于覆盖信息栏的 `name`、`charter`、`level`、`composer`）
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/result`
- `DELETE /api/v1/jobs/{job_id}`

`fit_official_divisions` 默认关闭；前端可在“高级设置”中显式开启，CLI 可使用
`--fit-official-divisions`，也可在 `render_config.json` 中设置 `"FIT_OFFICIAL_DIVISIONS": true`。

任务结果默认保留 30 分钟，服务重启会清理旧任务。可通过 `RPE_RESULT_TTL_SECONDS`、`RPE_RENDER_WORKERS`、`RPE_MAX_QUEUE_SIZE`、`RPE_MAX_UPLOAD_BYTES` 和 `RPE_RATE_LIMIT_PER_MINUTE` 调整限制；本地使用可设置 `RPE_LOCAL_MODE=true`。
