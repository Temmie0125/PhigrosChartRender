# RPE 谱面配置预览图生成器

输入 RPE（Re:PhiEdit）谱面 JSON 文件，输出一张纵向时间轴式的谱面配置预览 PNG。
所有判定线的音符合并到统一时间轴上，直观展示音符分布、密度变化、多押情况与 Hold 轨迹。

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
- **底部信息栏**：曲名、时长、难度、曲师、谱师、BPM 范围（最低~最高）与四类 Note 统计（按类型着色），双边框卡片样式，背景与主区共用整图模糊曲绘
- **可选背景**：曲绘高斯模糊（σ=15）作为整体背景，不指定则输出透明底 PNG；也可选择 JPG 输出以减小文件体积
- **预览区底色**：谱面预览区叠加可配置透明度的半透明黑色底色，压暗背景突出白色标记与 Note
- **自定义字体**：所有渲染文字（拍号/BPM/时值/计数/信息栏）统一使用可配置的主字体（默认 `resources/fonts/phi.ttf`），信息栏中文在字体缺字时按字形回退到系统 CJK 字体
- **配置文件**：所有渲染参数可通过 `render_config.json` 覆盖默认值，无需修改代码

## 环境要求

- Python ≥ 3.10
- matplotlib ≥ 3.7.0
- numpy ≥ 1.24.0
- Pillow ≥ 10.0.0

```bash
pip install -r requirements.txt
```

## 使用方法

```bash
# 基本用法
python -m rpe_render chart.json

# 指定背景曲绘与输出路径
python -m rpe_render chart.json --background art.png -o output.png
# JPG 输出（文件体积更小）
python -m rpe_render chart.json --background art.png -o output.jpg --format jpg

# 全部参数
python -m rpe_render chart.json --bg art.png -o out.png --dpi 300 --notes-dir resources/notes --preview-bg-alpha 0.4 --track-bg-alpha 0.75 --config render_config.json
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `chart` | RPE JSON 谱面文件路径（必填） | - |
| `--config` | 配置文件路径（JSON，覆盖 constants 默认值） | 当前目录下 `render_config.json` |
| `--background` / `--bg` | 背景曲绘图片路径 | 无（透明背景） |
| `-o` / `--output` | 输出图片路径 | `output.png` |
| `--format` | 输出格式：`png` / `jpg`；省略时按输出扩展名推断 | - |
| `--dpi` | 输出 DPI | 150 |
| `--notes-dir` | Note 贴图目录 | `resources/notes` |
| `--preview-bg-alpha` | 谱面预览区半透明黑色底色透明度（0.0 关闭 ~ 1.0） | 0.55 |
| `--track-bg-alpha` | 每条 Note 轨道区域额外加深透明度（0.0 关闭 ~ 1.0） | 0.75 |

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
- 测试假定默认配置运行（仓库内不创建 `render_config.json` 时行为不变）

日志级别默认 `WARNING`，可通过环境变量开启调试：

```bash
RPE_RENDER_LOG_LEVEL=DEBUG python -m rpe_render chart.json
```

### 作为库调用

```python
from rpe_render.renderer import RenderConfig, render

render(RenderConfig(
    chart_path="chart.json",
    background_path="art.png",   # 可选
    output_path="preview.png",
    notes_dir="resources/notes",
    dpi=150,
    preview_bg_alpha=0.55,       # 预览区半透明黑底色透明度（0.0~1.0）
    track_bg_alpha=0.75,         # 轨道区域额外加深透明度（0.0~1.0）
))
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
`background_blur_sigma` 与 `background_brightness`；后两项和透明度属于高级设置，
通常应保持默认值。

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
- 根目录只有一个 JSON 时直接使用；多个 JSON 时必须由 `info.txt` 的 `Chart:` 声明。
- 曲绘优先读取 JSON 的 `META.background`，其次读取 `info.txt` 的 `Picture:`。
- 声明的曲绘不存在或不是 PNG/JPG/JPEG 时返回“未找到曲绘”。
- 声明路径区分大小写，允许空格，禁止系统保留字符和目录穿越。

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
rpe_render/
├── cli.py                  # argparse 命令行解析
├── renderer.py             # 主渲染协调器（编排各模块）
├── chart_parser.py         # RPE JSON 解析与验证
├── timeline.py             # 分栏与像素坐标映射（纯计算）
├── time_utils.py           # TimeT 三元组 ↔ 拍数转换
├── models.py               # 数据模型（ChartData / NoteRenderInfo 等）
├── note_renderer.py        # Note 贴图加载、多押判定、放置
├── hold_renderer.py        # Hold Body/Head/End/轨迹渲染
├── grid_renderer.py        # 网格线、拍号、BPM 标记
├── marker_renderer.py      # 时值间隔标记、累计计数标记
├── info_bar.py             # 底部信息栏
├── background.py           # 曲绘模糊背景、预览区/轨道加深覆盖层
├── fonts.py                # 自定义字体管理（FONT_PATH 加载、CJK 回退）
├── constants.py            # 所有可调常量集中管理（支持 render_config.json 覆盖）
└── easing/
    ├── functions.py        # 29 种缓动函数（移植自 TypeScript 版）
    ├── bezier.py           # 贝塞尔曲线缓动（256 段折线近似）
    └── event_evaluator.py  # 事件值求值（多层叠加 + 缓动截取）
```

架构遵循：

- **计算层**（parser/timeline/easing/time_utils）为纯函数、无 matplotlib 依赖，可独立测试；
- **渲染层**模块之间禁止相互依赖；
- 所有可调参数集中在 `constants.py`。

## 关键渲染规则

| 决策 | 方案 |
|---|---|
| 多押判定 | 映射到主谱面后的 `displayBeat` 相同才构成实际多押；浮点映射使用稳定舍入 |
| Hold Body | 始终竖直矩形拉伸；段内 Head/End 与 Body 同 X 对齐；跨栏分段各用段内 X（尾段/中段取本段起始时刻判定线 X 映射到本栏）；Body 向两端延伸 `HOLD_BODY_OVERLAP_PX`（默认 1px）重叠拼接，消除接缝；轨迹曲线仅当持续期内存在实际位移（像素 X 范围 ≥ `HOLD_TRAJECTORY_MIN_DISPLACEMENT_PX`，默认 1px）时渲染 |
| 时值间隔标记 | 仅 Tap+Hold 跨类型混合排序，间隔 ≤ 1/4 拍（16 分音符）标记 N 分音符刻度（label = 4/间隔拍数） |
| 位置重合标注 | 仅同一主谱面实际开始时间的 Note 参与判定；组内按真实 X 距离 ≤ `NOTE_OVERLAP_THRESHOLD_X`（默认 75）聚类，在组最右 Note 旁标注 "×n"；Hold 只以头部计入 |
| 判定线坐标 | 全部 4 层 `moveXEvents`/`moveYEvents`/`rotateEvents` 叠加；父线递归变换，`rotateWithFather` 控制角度继承 |
| BPM 因数 | `displayBeat = localBeat × bpmfactor`，Note、Hold、轨迹、标记和重合判断统一使用映射后的主谱面时间 |
| 忽略字段 | `above`/`yOffset`/`size`/`speed`/判定线视觉属性/extended 事件不参与预览 |
| isFake 音符 | 过滤不渲染 |

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
|[示例谱面](resources/chart.json)|本项目内置|[@Temmie0125](https://github.com/Temmie0125)|
|[示例曲绘](resources/ill.png)|网络|[@nanakaria](https://space.bilibili.com/12013555)|

>注意：示例曲绘仅用于展示本项目渲染效果，请勿用于其他用途。如版权所有者认为不妥，请联系作者移除。

## 非官方声明

本项目并非 Phigros 官方项目，也与南京鸽游网络有限公司（Pigeon Games）、Re:PhiEdit 及其开发者无任何官方合作或附属关系。

- 本项目是一个粉丝自制工具，仅供学习交流使用。

- 所有游戏素材（包括但不限于 Note 贴图等）的版权归其原始权利人所有。

- 使用本项目生成的预览图仅可用于谱面展示等合法用途，请勿用于任何侵犯第三方权益的场景。

## 免责声明

本程序按“现状”提供，不提供任何明示或暗示的担保，包括但不限于对适销性、特定用途适用性和非侵权性的担保。在任何情况下，作者或版权持有人均不对因使用本程序而引起的任何索赔、损害或其他责任负责，无论这些责任是基于合同、侵权还是其他原因。
