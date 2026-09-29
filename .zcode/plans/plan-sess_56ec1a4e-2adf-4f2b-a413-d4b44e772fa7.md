# 新增 BPM 缩放倍率（bpm_scale）功能

## 背景与目标
画布尺寸完全由"拍数"决定：高度 = 每栏拍数×96px + 信息栏 320px，宽度由栏数 `ceil(max_beat/column_beats)` 决定（`timeline.py:100/238-253`）。按 N 倍 BPM 书写的谱面（如 `Incyde.YbeLL.0/IN.json`，官谱格式，24 条判定线全部 `bpm:540`，实际 180）拍数为 3 倍 → 栏数与画布宽 3 倍 → 渲染超时。

新增参数 `bpm_scale`（默认 1 = 不缩放），将谱面**所有时间数值统一乘以 f**：音符 start/end 拍数、事件 start/end、BPMList 各事件时间，同时 **BPM 数值也乘以 f**（540→180，与你确认的"标记按缩放后 BPM"一致；由于拍数与 BPM 同乘 f，真实秒时长不变，信息栏时长文本保持正确）。下游所有计算（max_beat、智能分栏、beat→像素、事件插值、Hold 分段、受影响段、拍号/时值/计数/BPM 标记）自动跟随，零逐点修改。

取值：仅 7 档位 `1/4、1/3、1/2、1、2、3、4`（容差匹配，支持 `"1/3"` 分数与浮点两种写法，其他值报错）。范围：仅渲染器仓库，不改 phi-plugin。

## 关键设计决策
1. **后处理统一变换**：新增 `scale_chart_time(chart, factor)`，在 `render()` 中解析之后调用一次。
2. **缩放时机：在 `fit_official_divisions` 之后**（`renderer.py:202-206` 之后、metadata 覆盖之前）。拟合容差（1/16 拍）与分母上限 128 均按"谱面书写拍"定义，先缩放会破坏拟合；后缩放保证官谱自动拟合行为与今天完全一致（对 540 谱面拟合本来也基本无操作：3 倍 BPM 下官谱 T=1/32 拍粒度反而无量化漂移）。
3. **TimeT 精确重建**：`BPMEvent.start_time`、`EventData.start_time/end_time`、`NoteData.raw_start_time/raw_end_time` 这些原始 TimeT 有直接消费者（`grid_renderer.py:113` BPM 标记位置、`timeline.py:204`、`info_bar.py:64-104`、遗留多押比较），用 `Fraction` 将 `[i,n,d]×f` 精确重建（如 `[1,1,2]×1/3 → [0,1,2]`），并同步重算 `EventData.start_beat/end_beat` 缓存。
4. **不缩放项**：`bpm_factor`（比值，缩放不变量）、`meta.duration`（秒数不变）、`meta.offset`、note 的 speed/floor_position（渲染未使用）、positionX 与事件值（空间量）。
5. f=1 时早退，行为零变化。

## 文件改动
### 新增 `rpe_render/time_scale.py`
- `ALLOWED_BPM_SCALES = (0.25, 1/3, 0.5, 1.0, 2.0, 3.0, 4.0)`
- `normalize_bpm_scale(value: float | str) -> float`：解析 `"1/3"` 或数值，isclose 匹配档位集合，非法抛 `ValueError`
- `scale_chart_time(chart: ChartData, factor: float) -> None`：遍历 `bpm_list`（start_time TimeT×f、bpm×f）、每条判定线（`line.bpm>0` 时×f、notes 的 beat×f + raw TimeT 重建、4 层 event_layers 全部 EventData 的 TimeT×f + beat 缓存重算）
- 内部 `_scale_timet(tt, factor)` 用 Fraction 精确缩放；空/异常输入原样返回

### `rpe_render/constants.py`
- 新增 `BPM_SCALE: float = 1.0`（配置文件覆盖机制自动生效）

### `rpe_render/renderer.py`
- `RenderConfig.__init__` 增加 `bpm_scale: float = BPM_SCALE`，用 `normalize_bpm_scale` 校验
- `render()` 在 `fit_official_divisions` 之后插入：`if config.bpm_scale != 1.0: scale_chart_time(chart, config.bpm_scale)`（附 log）

### `rpe_render/service.py`
- `render_source` 增加 `bpm_scale` kwarg，透传 RenderConfig

### `rpe_render/api.py`
- `RenderOptions` 增加 `bpm_scale: float` 字段
- `create_job` 的 Form 以字符串接收（兼容 `"1/3"` 与 `"0.333…"`），构造 options 前 `normalize_bpm_scale` 归一，失败返回 422 HTTPException
- `JobManager._run` 透传给 `render_source`

### `rpe_render/cli.py`
- 新增 `--bpm-scale`：type 为解析函数（支持分数/浮点），metavar `1/4|1/3|1/2|1|2|3|4`，默认取 `BPM_SCALE` 常量，help 说明场景

### `web/frontend/src/main.jsx`
- `DEFAULT_OPTIONS` 增加 `bpm_scale: 1`
- "03 输出设置"分栏模式后新增下拉框（7 档位，label "BPM 缩放倍率"，hint 说明"实际 BPM 与谱面书写 BPM 不一致时缩放时间轴，如实际 180 写作 540 选 1/3"）；FormData 经现有 `Object.entries` 循环自动携带；如 `style.css` 缺 select 样式则补一条

### `render_config.example.json` + 文档
- 示例配置增加 `BPM_SCALE` 键
- README.md（CLI 参数 + 功能说明段落）、docs/web_api.md（jobs 接口参数表）更新

### 新增 `tests/test_time_scale.py`
- 档位校验（含 `"1/3"` 字符串、非法值报错）
- scale_chart_time 单测：beat×f、bpm×f、TimeT 精确重建、bpm_factor 不变、EventData 缓存一致（构造方式参照现有 tests 风格）
- 集成断言：540 官谱 ×1/3 后 `compute_max_beat` 为原 1/3、`compute_canvas_size` 宽度等比缩小、`compute_duration_seconds` 不变
- RenderConfig 非法值抛 ValueError

## 验证
1. `python -m pytest tests/` 全量回归
2. 用真实谱面对比渲染：`python -m rpe_render <Incyde IN.json> --bpm-scale 1/3` vs 默认，确认宽度约 1/3、BPM 标记显示 180、时长文本不变、Note 布局等价压缩
3. 通过 API Form 提交 `bpm_scale=1/3` 验证端到端（必要时浏览器过一遍 Web UI）