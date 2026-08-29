# Web UI 与 API

Web UI 使用 React + Vite，后端使用 FastAPI 提供异步渲染任务。前端不直接解析谱面，
而是先上传文件读取元数据，再创建渲染任务。

## 本地启动

在项目根目录安装 Python 依赖并启动 API：

```bash
pip install -r requirements.txt
uvicorn rpe_render.api:app --reload --port 8000
```

另开终端启动 React/Vite 前端：

```bash
cd web/frontend
npm install
npm run dev
```

默认前端访问 `http://localhost:5173`，API 为 `http://127.0.0.1:8000`。如 API 地址不同，
设置 `VITE_API_BASE_URL`：

```bash
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

## UI 功能

- 支持点击或拖拽上传 `.json`、`.pez`、`.zip` 谱面文件。
- 加载后自动读取并编辑谱面名称、谱师、难度、曲师；编辑值只覆盖当前渲染任务。
- 基础配置可选择 PNG/JPG 输出，以及每栏拍数“自动”或“自定义”；自动为默认值，自定义范围为 16–128，以 4 拍为一档。
- 高级设置包括 DPI、预览/轨道透明度、曲绘模糊强度和亮度。
- “官谱分音拟合”属于实验性选项，默认关闭；仅建议用于官谱转换得到的 RPE 谱面。
- 渲染过程中显示队列状态与进度，完成后可预览并下载结果。

## API

### 元数据读取

`POST /api/v1/charts/metadata`

请求为 `multipart/form-data`，字段 `file` 必填。接口只读取并返回：

```json
{
  "name": "曲名",
  "charter": "谱师",
  "level": "AT 14",
  "composer": "曲师"
}
```

该接口不创建渲染任务。读取阶段允许谱面暂时缺少曲绘；正式渲染仍会按谱面包规则校验曲绘。

### 创建渲染任务

`POST /api/v1/jobs` 返回 `202` 和任务 ID。字段 `file` 必填，其余字段可选：

| 字段 | 类型 / 默认值 | 说明 |
|---|---|---|
| `smart_column_beats` | `true` | 自动选择每栏拍数，使画布比例尽量接近 16:9 |
| `column_beats` | `64` | 关闭自动选择时的每栏拍数，16–128 且为 4 的倍数 |
| `format` | `png` | `png` 或 `jpg` |
| `dpi` | `150` | 输出 DPI，72–600 |
| `preview_bg_alpha` | `0.55` | 预览区黑色覆盖层透明度，0–1 |
| `track_bg_alpha` | `0.75` | 轨道加深透明度，0–1 |
| `background_blur_sigma` | `15` | 曲绘高斯模糊强度，0–100 |
| `background_brightness` | `0.75` | 曲绘亮度，0–2 |
| `fit_official_divisions` | `false` | 实验性官谱分音拟合 |
| `name` | 空 | 覆盖信息栏谱面名称 |
| `charter` | 空 | 覆盖信息栏谱师 |
| `level` | 空 | 覆盖信息栏难度 |
| `composer` | 空 | 覆盖信息栏曲师 |

### 查询、下载与删除

- `GET /api/v1/health`：健康检查。
- `GET /api/v1/jobs/{job_id}`：查询任务状态、进度和错误信息。
- `GET /api/v1/jobs/{job_id}/result`：任务成功后下载图片。
- `DELETE /api/v1/jobs/{job_id}`：删除任务及其临时结果。

任务结果默认保留 30 分钟，服务重启会清理旧任务。可通过环境变量调整：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `RPE_RENDER_WORKERS` | `1` | 并发渲染 worker 数 |
| `RPE_MAX_QUEUE_SIZE` | `32` | 最大排队/运行任务数 |
| `RPE_MAX_UPLOAD_BYTES` | `268435456` | 上传文件上限 |
| `RPE_RESULT_TTL_SECONDS` | `1800` | 结果保留时间 |
| `RPE_RATE_LIMIT_PER_MINUTE` | `60` | 单 IP 每分钟创建任务数；设为 `0` 关闭 |
| `RPE_LOCAL_MODE` | `false` | `true` 时关闭 IP 频率限制 |
| `RPE_CORS_ORIGINS` | `localhost:5173` | 允许的前端来源，逗号分隔 |

## 部署

使用 Docker Compose：

```bash
docker compose up --build
```

默认前端地址为 `http://localhost:8080`，API 地址为 `http://localhost:8000`。
生产环境部署静态前端时，将 `VITE_API_BASE_URL` 设置为公开 API 地址，并在后端配置
`RPE_CORS_ORIGINS`。
