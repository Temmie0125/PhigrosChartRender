# RPE 谱面配置预览图生成器

输入 RPE（Re:PhiEdit）谱面 JSON 文件，输出一张纵向时间轴式的谱面配置预览 PNG。
所有判定线的音符合并到统一时间轴上，直观展示音符分布、密度变化、多押情况与 Hold 轨迹。

效果预览：
![效果图](/resources/example.png "示例谱面预览效果图")

## 功能特性

- **下落式时间轴**：时间从下往上递增，每 64 拍（16 小节）为一栏，超长谱面自动横向分栏
- **完整缓动支持**：29 种标准缓动 + 缓动截取（easingLeft/Right）+ 贝塞尔曲线缓动，判定线 X 坐标按 4 层事件叠加计算
- **Note 贴图渲染**：Tap / Drag / Flick / Hold 使用原版贴图，多押自动切换高亮（HL）贴图
- **Hold 渲染**：Body 竖直拉伸、Head/End 贴图、运动轨迹曲线，跨栏自动分段
- **时间轴标记**：拍线/小节线网格、拍号、BPM 变化、Note 时值间隔标记、每 4 拍累计计数（白色标记文字）
- **底部信息栏**：曲名、时长、难度、曲师、谱师、基准 BPM 与四类 Note 统计
- **可选背景**：曲绘高斯模糊（σ=15）作为整体背景，不指定则输出透明底 PNG
- **预览区底色**：谱面预览区叠加可配置透明度的半透明黑色底色，压暗背景突出白色标记与 Note

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

# 全部参数
python -m rpe_render chart.json --bg art.png -o out.png --dpi 300 --notes-dir resources/notes --preview-bg-alpha 0.4
```

| 参数 | 说明 | 默认值 |
|---|---|---|
| `chart` | RPE JSON 谱面文件路径（必填） | - |
| `--background` / `--bg` | 背景曲绘图片路径 | 无（透明背景） |
| `-o` / `--output` | 输出 PNG 路径 | `output.png` |
| `--dpi` | 输出 DPI | 150 |
| `--notes-dir` | Note 贴图目录 | `resources/notes` |
| `--preview-bg-alpha` | 谱面预览区半透明黑色底色透明度（0.0 关闭 ~ 1.0） | 0.55 |

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
))
```

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
├── background.py           # 曲绘模糊背景
├── constants.py            # 所有可调常量集中管理
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
| 多押判定 | startTime 三元组 `[a,b,c]` 分量完全相同才构成多押（整数精确比较） |
| Hold Body | 始终竖直矩形拉伸；Head/End 与 Body 同 X 对齐；轨迹曲线独立叠加 |
| 时值间隔标记 | 仅 Tap+Hold 跨类型混合排序，间隔 ≤ 1/4 拍（16 分音符）标记 N 分音符刻度（label = 4/间隔拍数） |
| 判定线 X | 全部 4 层 moveXEvents 同时刻值直接求和 |
| 忽略字段 | `above`/`yOffset`/`size`/`speed`/旋转/extended 事件不参与预览 |
| isFake 音符 | 过滤不渲染 |

