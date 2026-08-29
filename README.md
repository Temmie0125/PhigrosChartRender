# Phigros谱面配置预览图生成器

输入 RPE（Re:PhiEdit）/ 官谱谱面 JSON、PEZ 或 ZIP 谱面包，输出纵向时间轴式的谱面预览图。
所有判定线的音符会映射到统一主时间轴，直观展示音符分布、密度变化、多押情况与 Hold 轨迹。

效果预览：
![效果图](/resources/example.png "示例谱面预览效果图")

## 功能特性

- **下落式时间轴**：时间从下往上递增，每 64 拍（16 小节）为一栏，超长谱面自动横向分栏
- **完整缓动支持**：29 种标准缓动 + 缓动截取（easingLeft/Right）+ 贝塞尔曲线缓动，判定线 X 坐标按 4 层事件叠加计算
- **Note 贴图渲染**：Tap / Drag / Flick / Hold 使用原版贴图，多押自动切换高亮（HL）贴图
- **Hold 渲染**：Body 竖直拉伸、Head/End 贴图、运动轨迹曲线（仅持续期内存在实际位移时渲染），跨栏自动分段；Body 向 Head/End 贴图内侧延伸重叠拼接，消除接缝（与游戏内一致）
- **时间轴标记**：拍线/小节线灰色网格、拍号、BPM 变化、Note 时值间隔标记、每 4 拍累计计数（白色标记文字）
- **轨道加深**：每条 Note 轨道（栏内竖直区域，不含轨道间隔栏）叠加可配置透明度的加深底色，提高相邻轨道区分度
- **位置重合标注**：同一开始时间的 Note 中，谱面原始 X 距离 ≤ 阈值（默认 75）的组，在其旁边标注 "×n"（Hold 仅以头部参与）
- **Note 炸弹防御**：同一时刻、同一位置且几何完全一致的重复 Note 默认最多实际绘制 4 个，并优先覆盖四种 Note 类型；统计、Combo 与数量标注仍使用完整 Note 列表
- **官谱 JSON 适配**：自动识别官谱格式，支持每条判定线独立 BPM、官谱 Note 类型与事件；官谱坐标会按比例映射到 RPE 轨道坐标系，并自动启用分音拟合
- **底部信息栏**：曲名、时长、难度、曲师、谱师、BPM 范围（最低~最高）与四类 Note 统计（按类型着色），双边框卡片样式，背景与主区共用整图模糊曲绘
- **可选背景与格式**：曲绘高斯模糊（σ=15）作为整体背景；不指定背景时 PNG 输出透明底，也可输出 JPG 以减小文件体积
- **Web UI 元数据编辑**：加载谱面后可编辑谱面名称、谱师、难度、曲师，修改只作用于当前渲染任务
- **预览区底色**：谱面预览区叠加可配置透明度的半透明黑色底色，压暗背景突出白色标记与 Note
- **自定义字体**：所有渲染文字（拍号/BPM/时值/计数/信息栏）统一使用可配置的主字体（默认 `resources/fonts/phi.ttf`），信息栏中文在字体缺字时按字形回退到系统 CJK 字体
- **配置文件**：所有渲染参数可通过 `render_config.json` 覆盖默认值，无需修改代码

## 环境要求

- Python ≥ 3.10
- matplotlib ≥ 3.7.0
- numpy ≥ 1.24.0
- Pillow ≥ 10.0.0
- Node.js ≥ 18（仅运行 Web UI 时需要）

```bash
pip install -r requirements.txt
```

## 使用方法

```bash
# JSON、PEZ、ZIP 均可直接作为输入
python -m rpe_render chart.json
python -m rpe_render chart.pez

# 指定背景曲绘与输出路径
python -m rpe_render chart.json --background art.png -o output.png
# JPG 输出（文件体积更小）
python -m rpe_render chart.json --background art.png -o output.jpg --format jpg

# 对 RPE 谱面显式开启实验性官谱分音拟合（官谱会自动启用）
python -m rpe_render chart.json --fit-official-divisions

# 按谱面长度智能选择每栏拍数，使输出比例接近 16:9（覆盖 COLUMN_BEATS）
python -m rpe_render chart.json --smart-column-beats

# 常用参数组合
python -m rpe_render chart.json --bg art.png -o out.jpg --format jpg --dpi 300 \
  --preview-bg-alpha 0.4 --track-bg-alpha 0.75 --config render_config.json
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `chart` | RPE JSON、PEZ 或 ZIP 谱面文件路径（必填） | - |
| `--config` | 配置文件路径（JSON，覆盖 constants 默认值） | 当前目录下 `render_config.json` |
| `--background` / `--bg` | 背景曲绘图片路径 | 无（透明背景） |
| `-o` / `--output` | 输出图片路径 | `output.png` |
| `--format` | 输出格式：`png` / `jpg`；省略时按输出扩展名推断 | 按扩展名推断 |
| `--dpi` | 输出 DPI | 150 |
| `--notes-dir` | Note 贴图目录 | `resources/notes` |
| `--preview-bg-alpha` | 谱面预览区半透明黑色底色透明度（0.0 关闭 ~ 1.0） | 0.55 |
| `--track-bg-alpha` | 每条 Note 轨道区域额外加深透明度（0.0 关闭 ~ 1.0） | 0.75 |
| `--fit-official-divisions` | 启用官谱分音拟合（实验性，仅 Tap/Hold） | 关闭 |
| `--smart-column-beats` | 按谱面总拍数自动选择每栏拍数，使最终图像比例接近 16:9；覆盖 `COLUMN_BEATS` | 关闭 |

输入为 PEZ/ZIP 时，程序会安全解包并定位曲绘；不会修改原始压缩包。
谱面包信息文件按以下顺序回退：`info.txt` → 与谱面 JSON 同名的 `.txt` → 包内唯一 `.txt`。
其中 `Name`、`Level`、`Composer`、`Charter` 会作为底部信息栏默认元数据，显式指定的元数据优先。
官谱包没有资源声明时，曲绘优先使用包内唯一 PNG/JPG/JPEG，再回退到信息文件中的 `Picture:`。

> **关于官谱适配与分音拟合：**
> 官谱 JSON 的时间单位为各判定线 BPM 下的 1/32 拍，Note type 顺序为 Tap/Drag/Hold/Flick，且不同判定线可以使用不同 BPM。渲染器会将这些时间统一映射到主时间轴，并将官谱横向坐标按比例映射到 RPE 的 `[-675, 675]` 范围。
> 官谱只支持 2 的整数次幂分音，12、20、24 等特殊分音通常由密集 Note 近似产生。官谱检测到后会自动执行拟合；RPE JSON 仍需通过 `--fit-official-divisions` 显式开启。

> RPE JSON**原生支持**任意分音，**通常无需开启**此选项。如果你的RPE JSON**由官谱转换而来**或者**确认需要**开启，请注意：
> 官谱拟合会以至少 3 个连续间隔为候选序列，并以 1/16 拍作为最大允许误差；
> 精确的 16/32/64 等原生分音会作为边界，避免不同节奏段互相吸附。该功能属于实验性启发式算法，
> 开启后应检查关键段落的渲染结果。

### 配置文件

所有渲染参数（拍高、栏宽、颜色、透明度、贴图路径等）都可通过 JSON 配置文件覆盖，无需修改代码：

```bash
# 复制示例文件并编辑
cp render_config.example.json render_config.json
# 或显式指定路径
python -m rpe_render chart.json --config my_settings.json
```

- 配置文件键名对应 `constants.py` 中的常量名，**大小写不敏感**（如 `beat_height_px` 等价于 `BEAT_HEIGHT_PX`）
- 主字体通过 `FONT_PATH` 配置（默认 `resources/fonts/phi.ttf`，相对仓库根目录或绝对路径）；文件缺失或加载失败时回退到系统默认字体并告警
- 未知键与类型不匹配的键会被忽略并发出警告；以 `_` 开头的键视为注释
- 查找顺序：`--config` 参数 > 环境变量 `RPE_RENDER_CONFIG` > 当前目录下 `render_config.json`
- 参数优先级：命令行参数 > 配置文件 > 代码默认值
- `FIT_OFFICIAL_DIVISIONS` 默认 `false`，`SMART_COLUMN_BEATS` 默认 `false`，`NOTE_BOMB_RENDER_LIMIT` 默认 `4`
- 开启 `SMART_COLUMN_BEATS`（或命令行 `--smart-column-beats`、WebUI 高级设置）后，渲染器根据谱面最大拍数选择每栏拍数，并覆盖固定的 `COLUMN_BEATS`；关闭时保持固定分栏行为。
- 测试假定默认配置运行（仓库内不创建 `render_config.json` 时行为不变）

日志级别默认 `WARNING`，可通过环境变量开启调试：

```bash
RPE_RENDER_LOG_LEVEL=DEBUG python -m rpe_render chart.json
```

### 作为库调用

```python
from rpe_render.renderer import RenderConfig, render

render(RenderConfig(
    chart_path="chart.json",     # 也可以是已解包后的 JSON 路径
    background_path="art.png",   # 可选
    output_path="preview.png",
    notes_dir="resources/notes",
    smart_column_beats=False,      # 按谱面长度自动调节每栏拍数，默认关闭
    dpi=150,
    preview_bg_alpha=0.55,       # 预览区半透明黑底色透明度（0.0~1.0）
    track_bg_alpha=0.75,         # 轨道区域额外加深透明度（0.0~1.0）
    fit_official_divisions=False, # 实验性官谱分音拟合，默认关闭
))
```

PEZ/ZIP 等谱面包建议使用服务层接口，它会负责临时解包、曲绘定位和清理：

```python
from rpe_render.service import render_source

image = render_source(
    "chart.pez",
    output_format="png",
    fit_official_divisions=True,
    metadata={"name": "自定义标题", "level": "AT 14"},
)
open("preview.png", "wb").write(image)
```

库调用若要使用配置文件，在导入 `rpe_render` 渲染模块前调用：

```python
from rpe_render import constants

constants.load_config("my_settings.json")  # 覆盖默认常量
from rpe_render.renderer import RenderConfig, render
```

## Web API 与前端

### 启动 API

```bash
uvicorn rpe_render.api:app --host 127.0.0.1 --port 8000
```

API 使用内存任务队列和本地临时目录。任务结果默认保留 30 分钟，服务重启时自动删除旧任务。

前端会先调用 `POST /api/v1/charts/metadata` 读取谱面元数据，再将用户编辑的
`name`、`charter`、`level`、`composer` 作为表单字段提交到 `POST /api/v1/jobs`。
任务还支持 `format`（`png`/`jpg`）、`dpi`、`preview_bg_alpha`、`track_bg_alpha`、
`background_blur_sigma`、`background_brightness`、`fit_official_divisions` 与 `smart_column_beats`；这些参数属于高级设置，
通常应保持默认值。

`FIT_OFFICIAL_DIVISIONS` / `--fit-official-divisions` 可为 RPE 谱面显式开启实验性的分音拟合，
默认关闭；官谱检测到后会自动开启。它只调整 Tap/Hold 起始时间，Drag/Flick 不参与拟合。

### API 请求字段

`POST /api/v1/charts/metadata` 和 `POST /api/v1/jobs` 均使用 `multipart/form-data`，
字段 `file` 必填，支持 `.json`、`.pez`、`.zip`。

| 字段 | 类型/默认值 | 说明 |
|---|---|---|
| `format` | `png` | `png` 或 `jpg` |
| `dpi` | `150` | 72–600 |
| `preview_bg_alpha` | `0.55` | 预览区黑色覆盖层透明度 |
| `track_bg_alpha` | `0.75` | 轨道加深透明度 |
| `background_blur_sigma` | `15` | 曲绘高斯模糊强度，0–100 |
| `background_brightness` | `0.75` | 曲绘亮度，0–2 |
| `fit_official_divisions` | `false` | 实验性官谱分音拟合 |
| `smart_column_beats` | `false` | 按谱面总拍数自动选择每栏拍数，使画布比例接近 16:9；覆盖 `COLUMN_BEATS` |
| `name` / `charter` / `level` / `composer` | 空 | 覆盖底部信息栏对应字段 |

`POST /api/v1/charts/metadata` 只解析并返回四项可编辑元数据，不创建渲染任务。
任务接口返回 `202` 和任务 ID，通过 `GET /api/v1/jobs/{job_id}` 轮询；完成后从
`GET /api/v1/jobs/{job_id}/result` 下载图片。

可配置环境变量：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `RPE_RENDER_WORKERS` | `1` | 并发渲染 worker 数 |
| `RPE_MAX_QUEUE_SIZE` | `32` | 最大排队/运行任务数 |
| `RPE_MAX_UPLOAD_BYTES` | `268435456` | 上传文件上限 |
| `RPE_RESULT_TTL_SECONDS` | `1800` | 结果保留时间 |
| `RPE_RATE_LIMIT_PER_MINUTE` | `60` | 单 IP 每分钟创建任务数；设为 `0` 关闭 |
| `RPE_LOCAL_MODE` | `false` | `true` 时关闭 IP 频率限制 |
| `RPE_CORS_ORIGINS` | `localhost:5173` | 允许的前端来源，逗号分隔 |

### 谱面包规则

- 支持 `.pez`、`.zip` 和 `.json`。
- 根目录只有一个 JSON 时直接使用；多个 JSON 时必须由信息文件的 `Chart:` 声明。
- 信息文件按 `info.txt` → 与谱面 JSON 同名的 `.txt` → 包内唯一 `.txt` 回退选择。
- `Name`、`Level`、`Composer`、`Charter` 用于补充官谱缺失的 JSON `META`；JSON 中非空字段优先。
- RPE 曲绘优先读取 JSON 的 `META.background`，其次读取信息文件的 `Picture:`。
- 官谱没有资源声明时，优先使用包内唯一 PNG/JPG/JPEG 图片，其次使用信息文件的 `Picture:`。
- 声明的曲绘不存在或不是 PNG/JPG/JPEG 时返回“未找到曲绘”。
- 声明路径**区分大小写**，**允许空格**，**禁止系统保留字符**和**目录穿越**。

### 前端

```bash
cd web/frontend
npm install
npm run dev
```

设置 `VITE_API_BASE_URL` 指向 API 服务即可将前端部署到任意静态托管平台（包括 Vercel）。

### Docker Compose

```bash
docker compose up --build
```

前端地址为 `http://localhost:8080`，API 地址为 `http://localhost:8000`。

## 项目结构

```
.
├── rpe_render/
│   ├── api.py              # FastAPI：上传、任务队列、元数据接口与结果下载
│   ├── cli.py              # argparse 命令行解析
│   ├── service.py          # 可复用服务层：谱面包加载 + 内存图片输出
│   ├── renderer.py         # 主渲染协调器（编排各模块）
│   ├── division_fit.py     # 实验性官谱非 2 次幂分音拟合
│   ├── package_loader.py   # JSON/PEZ/ZIP 安全加载、解包与曲绘定位
│   ├── chart_parser.py     # RPE JSON 解析与验证
│   ├── timeline.py         # 分栏与像素坐标映射（纯计算）
│   ├── time_utils.py       # TimeT 三元组 ↔ 拍数转换
│   ├── models.py           # 数据模型（ChartData / NoteRenderInfo 等）
│   ├── note_renderer.py    # Note 贴图加载、多押判定、炸弹防御与放置
│   ├── hold_renderer.py    # Hold Body/Head/End/轨迹渲染
│   ├── grid_renderer.py    # 网格线、拍号、BPM 标记
│   ├── marker_renderer.py  # 时值间隔标记、累计计数标记
│   ├── info_bar.py         # 底部信息栏
│   ├── background.py       # 曲绘模糊背景、预览区/轨道加深覆盖层
│   ├── fonts.py            # 自定义字体管理（FONT_PATH 加载、CJK 回退）
│   ├── constants.py        # 所有可调常量集中管理
│   └── easing/             # 缓动函数、贝塞尔与事件求值
├── web/
│   ├── README.md           # Web UI/API 快速说明
│   └── frontend/           # React + Vite 前端
├── tests/                  # 计算、渲染、API 相关回归测试
├── resources/              # Note 贴图、字体、示例谱面与曲绘
├── render_config.example.json
├── requirements.txt
└── docker-compose.yml
```

架构遵循：

- **输入层**：`package_loader` 负责格式识别、安全解包和曲绘定位，`chart_parser` 负责结构验证与模型化；
- **预处理层**：可选的 `division_fit` 只在显式开启时调整 Tap/Hold 起始时间；
- **计算层**：`timeline`、`easing`、`time_utils` 计算统一主时间轴、判定线姿态和像素几何；
- **渲染层**：`grid_renderer`、`note_renderer`、`hold_renderer`、`affected_area_renderer` 等绘制前景；
- **输出层**：`background` 合成曲绘/JPG，`info_bar` 绘制元信息和统计；
- **适配层**：`cli` 面向命令行，`service` 面向库调用和 API，`api` 提供异步任务接口；
- 所有可调参数集中在 `constants.py`，通过配置文件覆盖；默认关闭的实验性能力不会改变普通渲染路径。

### 一次渲染的主要流程

```text
JSON / PEZ / ZIP
      │
      ▼
安全加载与谱面解析 ──► 官谱自动适配/分音拟合（RPE 可选开启）
      │
      ▼
统一主时间轴与判定线姿态计算
      │
      ▼
网格 / Hold / Note / 受影响区域 / 标记 / 信息栏
      │
      ▼
透明前景 + 曲绘合成 ──► PNG 或 JPG
```

## 关键渲染规则

| 决策 | 方案 |
|---|---|
| 多押判定 | 映射到主谱面后的 `displayBeat` 相同才构成实际多押；浮点映射使用稳定舍入 |
| Hold Body | 始终竖直矩形拉伸；段内 Head/End 与 Body 同 X 对齐；跨栏分段各用段内 X（尾段/中段取本段起始时刻判定线 X 映射到本栏）；Body 向两端延伸 `HOLD_BODY_OVERLAP_PX`（默认 1px）重叠拼接，消除接缝；轨迹曲线仅当持续期内存在实际位移（像素 X 范围 ≥ `HOLD_TRAJECTORY_MIN_DISPLACEMENT_PX`，默认 1px）时渲染 |
| 时值间隔标记 | 仅 Tap+Hold 跨类型混合排序，间隔 ≤ 1/4 拍（16 分音符）标记 N 分音符刻度（label = 4/间隔拍数） |
| 位置重合标注 | 仅同一主谱面实际开始时间的 Note 参与判定；组内按真实 X 距离 ≤ `NOTE_OVERLAP_THRESHOLD_X`（默认 75）聚类，在组最右 Note 旁标注 "×n"；Hold 只以头部计入 |
| Note 炸弹防御 | 仅对同一实际开始时间、精确相同渲染位置且几何完全一致的重复 Note 生效；默认最多绘制 4 个，按类型轮询优先覆盖 Tap/Hold/Flick/Drag；原始 Note 仍用于数量标注与统计 |
| 判定线坐标 | 全部 4 层 `moveXEvents`/`moveYEvents`/`rotateEvents` 叠加；父线递归变换，`rotateWithFather` 控制角度继承 |
| BPM 因数 | `displayBeat = localBeat × bpmfactor`，Note、Hold、轨迹、标记和重合判断统一使用映射后的主谱面时间 |
| 忽略字段 | `above`/`yOffset`/`size`/`speed`/判定线视觉属性/extended 事件不参与预览 |
| isFake 音符 | 过滤不渲染 |
| 官谱分音拟合 | 官谱自动执行，RPE 仅显式开启；以连续高密度 Tap/Hold 起始时间推断非 2 次幂分音，误差上限 1/16 拍；精确原生分音作为边界 |

## 测试

```bash
python -m pytest tests/ -v
```

测试分层：纯计算单元测试（time_utils/easing/parser/timeline/marker 等）→
渲染层集成测试（检查 Axes 状态）→ E2E 测试（真实谱面 `resources/chart.json` 出图验证）。

## RPE支持说明

理论上支持现有的几乎所有 RPE 特性（包括分层事件、递归父子线和 BPM 因数；第五层事件自动忽略，也不考虑缩放等特殊视觉事件）。配置渲染以 Note 的实际落点和主谱面时间为准。

## 许可证

本项目采用 **GNU General Public License v3.0** 进行许可。  

您可以在项目根目录下的 [LICENSE](LICENSE) 文件中查看完整的许可证文本，或访问 [GNU 官网](https://www.gnu.org/licenses/gpl-3.0.html) 获取更多信息。

## 素材版权归属

本项目使用了以下第三方素材，其版权分别归属各自的权利人：

|素材类型|来源|版权归属|
|---|---|---|
|Note 贴图（Tap / Drag / Flick / Hold 等）|Phigros 游戏|南京鸽游网络有限公司（Pigeon Games）|
|[字体文件](resources/fonts/phi.ttf)|思源黑体（Source Han Sans / Noto Sans CJK）|Adobe Systems Incorporated（依据 SIL Open Font License v1.1 授权）|
|[示例谱面](resources/chart.json)|本项目内置|[@Temmie0125](https://github.com/Temmie0125)|
|[示例曲绘](resources/ill.png)|网络|[@nanakaria](https://space.bilibili.com/12013555)|

>关于字体：本字体依据 SIL Open Font License v1.1 协议分发，您可以在遵守该协议的前提下自由使用、修改与再分发。

>注意：示例曲绘仅用于展示本项目渲染效果，请勿用于其他用途。如版权所有者认为不妥，请联系作者移除。

## 非官方声明

本项目并非 Phigros 官方项目，也与南京鸽游网络有限公司（Pigeon Games）、Re:PhiEdit 及其开发者无任何官方合作或附属关系。

- 本项目是一个粉丝自制工具，仅供学习交流使用。

- 所有游戏素材（包括但不限于 Note 贴图等）的版权归其原始权利人所有。

- 使用本项目生成的预览图仅可用于谱面展示等合法用途，请勿用于任何侵犯第三方权益的场景。

## 免责声明

本程序按“现状”提供，不提供任何明示或暗示的担保，包括但不限于对适销性、特定用途适用性和非侵权性的担保。在任何情况下，作者或版权持有人均不对因使用本程序而引起的任何索赔、损害或其他责任负责，无论这些责任是基于合同、侵权还是其他原因。
